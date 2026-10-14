"""vn process: local work only (OCR and speech-to-text), no AI reasoning."""

import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytesseract

from . import db
from .config import ROOT, TOOLS, load, media_dir
from .ocr import ocr_image
from .transcribe import transcribe

MIN_TEXT_CHARS = 3  # an image needs at least this many letters/digits to count as having text


def has_text(text: str | None) -> bool:
    return sum(c.isalnum() for c in text or "") >= MIN_TEXT_CHARS


def setup_tesseract() -> None:
    """Use the system tesseract; without it, the copy unpacked from Fedora's RPMs into data/tools/."""
    if shutil.which("tesseract"):
        return
    local = TOOLS / "root/usr/bin/tesseract"
    if not local.exists():
        raise SystemExit("tesseract not found: sudo dnf install tesseract tesseract-langpack-ita tesseract-langpack-spa")
    pytesseract.pytesseract.tesseract_cmd = str(local)
    os.environ["TESSDATA_PREFIX"] = str(TOOLS / "tessdata")


def run_ocr(con, post_ids: list[str], cfg: dict) -> None:
    if not post_ids:
        return
    marks = ",".join("?" * len(post_ids))
    todo = con.execute(
        f"SELECT post_id, idx, path FROM images WHERE ocr_text IS NULL AND post_id IN ({marks})", post_ids
    ).fetchall()
    if not todo:
        return
    langs = cfg["ocr"]["langs"]
    # One thread per tesseract: we run several in parallel. Set here, not at import time:
    # faster-whisper's OpenMP runtime would read it when loaded and drop to one thread.
    os.environ["OMP_THREAD_LIMIT"] = "1"
    t0 = time.time()
    with ThreadPoolExecutor(cfg["ocr"].get("workers", 8)) as pool:
        futures = {pool.submit(ocr_image, str(ROOT / r["path"]), langs): r for r in todo}
        for fut in as_completed(futures):
            r = futures[fut]
            text, conf = fut.result()
            con.execute("UPDATE images SET ocr_text = ?, ocr_conf = ? WHERE post_id = ? AND idx = ?",
                        (text, conf, r["post_id"], r["idx"]))
            con.commit()
    print(f"ocr: {len(todo)} images in {time.time() - t0:.0f} s")


def process(limit: int | None) -> int:
    cfg = load()
    setup_tesseract()
    con = db.connect()
    posts = con.execute("SELECT * FROM posts WHERE status = 'fetched' ORDER BY rowid LIMIT ?",
                        (limit or -1,)).fetchall()
    run_ocr(con, [p["id"] for p in posts], cfg)
    model = cfg["whisper"]["model"]
    for post in posts:
        pid = post["id"]
        audio = media_dir(pid) / "audio.wav"
        if post["type"] == "video" and not post["transcribed"]:
            fields = {"transcribed": 1, "whisper_model": model}
            if audio.exists():
                t0 = time.time()
                segs, lang, prob = transcribe(str(audio), model, cfg["whisper"]["compute_type"])
                con.execute("DELETE FROM segments WHERE post_id = ?", (pid,))
                con.executemany("INSERT INTO segments VALUES (?, ?, ?, ?, ?)",
                                [(pid, i, s["start"], s["end"], s["text"]) for i, s in enumerate(segs)])
                if segs:
                    fields |= {"language": lang, "language_prob": prob}
                print(f"transcribed {pid}: {len(segs)} segments, {lang} ({prob}), {time.time() - t0:.0f} s")
            con.execute(f"UPDATE posts SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                        [*fields.values(), pid])
            con.commit()
            audio.unlink(missing_ok=True)
        speech = con.execute("SELECT COUNT(*) FROM segments WHERE post_id = ?", (pid,)).fetchone()[0]
        texts = [r[0] for r in con.execute("SELECT ocr_text FROM images WHERE post_id = ?", (pid,))]
        if not speech and not any(has_text(t) for t in texts):
            db.set_status(con, pid, "skipped", skip_reason="no content")
            print(f"skipped {pid}: no content")
        else:
            db.set_status(con, pid, "processed")
            print(f"processed {pid}")
    return len(posts)
