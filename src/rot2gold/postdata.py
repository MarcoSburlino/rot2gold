"""A processed post's data for whoever writes its note: the record `r2g pending` shows."""

from .config import DATA


def fmt_time(s: float) -> str:
    return f"{int(s // 60)}:{s % 60:04.1f}"


def post_record(con, row) -> dict:
    images = con.execute("SELECT idx, kind, path, ocr_text, ocr_conf FROM images WHERE post_id = ? ORDER BY idx",
                         (row["id"],)).fetchall()
    segs = con.execute("SELECT start, end, text FROM segments WHERE post_id = ? ORDER BY idx", (row["id"],)).fetchall()
    return {
        "id": row["id"], "url": row["url"], "creator": row["creator"], "posted": row["upload_date"],
        "type": row["type"], "language": row["language"], "language_prob": row["language_prob"],
        "images": [{"kind": i["kind"], "n": i["idx"], "path": str(DATA / i["path"]),
                    "ocr_conf": i["ocr_conf"], "ocr_text": i["ocr_text"]} for i in images],
        "transcript": [dict(s) for s in segs],
    }


def post_text(p: dict) -> str:
    """A post as `r2g pending` prints it: OCR text with confidence and image paths, then the transcript."""
    out = [f"=== {p['id']} | {p['type']} | @{p['creator']} | posted {p['posted']}", f"url: {p['url']}"]
    if p["type"] == "video":
        out.append(f"speech language: {p['language'] or 'none detected'}"
                   + (f" (p={p['language_prob']})" if p["language"] else ""))
    for img in p["images"]:
        label = "On-screen text (0.5 s)" if img["kind"] == "frame" else f"Slide {img['n']}"
        out += [f"\n--- {label} | OCR confidence {img['ocr_conf']} | {img['path']}", img["ocr_text"] or "(no text)"]
    if p["type"] == "video":
        out.append("\n--- Transcript")
        if not p["transcript"]:
            out.append("(no speech)")
        out += [f"[{fmt_time(s['start'])}–{fmt_time(s['end'])}] {s['text']}" for s in p["transcript"]]
    return "\n".join(out) + "\n"
