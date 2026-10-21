"""r2g process: local work only (OCR and speech-to-text), no AI reasoning."""

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytesseract

from pathlib import Path

from . import db, tools
from .config import DATA, load, media_dir
from .events import echo
from .ocr import ocr_image
from .transcribe import transcribe

MIN_TEXT_CHARS = 3  # an image needs at least this many letters/digits to count as having text


def has_text(text: str | None) -> bool:
    return sum(c.isalnum() for c in text or "") >= MIN_TEXT_CHARS


def setup_tesseract(cfg: dict) -> bool:
    """Point pytesseract at Tesseract ([ocr] tesseract and tessdata, or what tools.tesseract finds).
    False if there is none."""
    exe = tools.tesseract(cfg)
    if not exe:
        return False
    pytesseract.pytesseract.tesseract_cmd = exe
    if cfg["ocr"].get("tessdata"):
        os.environ["TESSDATA_PREFIX"] = str(Path(cfg["ocr"]["tessdata"]).expanduser())
    return True


def run_ocr(con, post_ids: list[str], cfg: dict, report=echo) -> None:
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
        futures = {pool.submit(ocr_image, str(DATA / r["path"]), langs): r for r in todo}
        for fut in as_completed(futures):
            r = futures[fut]
            text, conf = fut.result()
            con.execute("UPDATE images SET ocr_text = ?, ocr_conf = ? WHERE post_id = ? AND idx = ?",
                        (text, conf, r["post_id"], r["idx"]))
            con.commit()
    report(f"ocr: {len(todo)} images in {time.time() - t0:.0f} s")


def process(limit: int | None = None, ids=None, report=echo) -> int:
    """OCR and transcribe up to `limit` fetched posts (only those in `ids`, if given). Returns how many."""
    cfg = load()
    con = db.connect()
    sql, args = "SELECT * FROM posts WHERE status = 'fetched'", []
    if ids is not None:
        if not ids:
            return 0
        sql += f" AND id IN ({db.placeholders(ids)})"
        args += list(ids)
    posts = con.execute(sql + " ORDER BY rowid LIMIT ?", [*args, limit or -1]).fetchall()
    if not posts:
        return 0
    if setup_tesseract(cfg):
        run_ocr(con, [p["id"] for p in posts], cfg, report)
    else:
        report(f"Tesseract isn't installed, so text on screen is not read (the AI can still look at the images)."
               f" To install it: {tools.install_hint('tesseract')}", level="warn")
    model = cfg["whisper"]["model"]
    for post in posts:
        pid = post["id"]
        audio = media_dir(pid) / "audio.wav"
        if post["type"] == "video" and not post["transcribed"]:
            fields = {"transcribed": 1, "whisper_model": model}
            done_msg = None
            if audio.exists():
                t0 = time.time()
                segs, lang, prob = transcribe(str(audio), model, cfg["whisper"]["compute_type"])
                con.execute("DELETE FROM segments WHERE post_id = ?", (pid,))
                con.executemany("INSERT INTO segments VALUES (?, ?, ?, ?, ?)",
                                [(pid, i, s["start"], s["end"], s["text"]) for i, s in enumerate(segs)])
                if segs:
                    fields |= {"language": lang, "language_prob": prob}
                done_msg = f"transcribed {pid}: {len(segs)} segments, {lang} ({prob}), {time.time() - t0:.0f} s"
            con.execute(f"UPDATE posts SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                        [*fields.values(), pid])
            con.commit()
            audio.unlink(missing_ok=True)
            if done_msg:  # only after the commit: a run's report writes to the database too
                report(done_msg, post_id=pid)
        speech = con.execute("SELECT COUNT(*) FROM segments WHERE post_id = ?", (pid,)).fetchone()[0]
        texts = [r[0] for r in con.execute("SELECT ocr_text FROM images WHERE post_id = ?", (pid,))]
        read = all(t is not None for t in texts)  # without OCR the images' text is unknown: never skip on it
        if read and not speech and not any(has_text(t) for t in texts):
            db.set_status(con, pid, "skipped", skip_reason="no content")
            report(f"skipped {pid}: no content", post_id=pid)
        else:
            db.set_status(con, pid, "processed")
            report(f"processed {pid}", post_id=pid)
    return len(posts)
