"""vn: TikTok collection → notes in the brain. See docs/spec.md."""

import argparse
import json
import sys

from . import db
from .config import ROOT


def fmt_time(s: float) -> str:
    return f"{int(s // 60)}:{s % 60:04.1f}"


def post_record(con, row) -> dict:
    images = con.execute("SELECT idx, kind, path, ocr_text, ocr_conf FROM images WHERE post_id = ? ORDER BY idx",
                         (row["id"],)).fetchall()
    segs = con.execute("SELECT start, end, text FROM segments WHERE post_id = ? ORDER BY idx", (row["id"],)).fetchall()
    return {
        "id": row["id"], "url": row["url"], "creator": row["creator"], "posted": row["upload_date"],
        "type": row["type"], "language": row["language"], "language_prob": row["language_prob"],
        "images": [{"kind": i["kind"], "n": i["idx"], "path": str(ROOT / i["path"]),
                    "ocr_conf": i["ocr_conf"], "ocr_text": i["ocr_text"]} for i in images],
        "transcript": [dict(s) for s in segs],
    }


def print_post(p: dict) -> None:
    print(f"=== {p['id']} | {p['type']} | @{p['creator']} | posted {p['posted']}")
    print(f"url: {p['url']}")
    if p["type"] == "video":
        print(f"speech language: {p['language'] or 'none detected'}"
              + (f" (p={p['language_prob']})" if p["language"] else ""))
    for img in p["images"]:
        label = "On-screen text (0.5 s)" if img["kind"] == "frame" else f"Slide {img['n']}"
        print(f"\n--- {label} | OCR confidence {img['ocr_conf']} | {img['path']}")
        print(img["ocr_text"] or "(no text)")
    if p["type"] == "video":
        print("\n--- Transcript")
        if not p["transcript"]:
            print("(no speech)")
        for s in p["transcript"]:
            print(f"[{fmt_time(s['start'])}–{fmt_time(s['end'])}] {s['text']}")
    print()


def cmd_pending(args) -> None:
    con = db.connect()
    rows = con.execute("SELECT * FROM posts WHERE status = 'processed' ORDER BY rowid LIMIT ?",
                       (args.n or -1,)).fetchall()
    if args.id:
        rows = con.execute("SELECT * FROM posts WHERE id = ?", (args.id,)).fetchall()
    records = [post_record(con, r) for r in rows]
    if args.json:
        json.dump(records, sys.stdout, ensure_ascii=False, indent=1)
        print()
        return
    if args.ids:
        print("\n".join(r["id"] for r in records))
        return
    for r in records:
        print_post(r)
    total = con.execute("SELECT COUNT(*) FROM posts WHERE status = 'processed'").fetchone()[0]
    print(f"({len(records)} shown, {total} pending)")


def cmd_done(args) -> None:
    con = db.connect()
    row = con.execute("SELECT status FROM posts WHERE id = ?", (args.id,)).fetchone()
    if not row:
        raise SystemExit(f"unknown post {args.id}")
    db.set_status(con, args.id, "done", note_path=args.note_path, skip_reason=None)
    print(f"done {args.id} → {args.note_path}")


def cmd_skip(args) -> None:
    con = db.connect()
    if not con.execute("SELECT 1 FROM posts WHERE id = ?", (args.id,)).fetchone():
        raise SystemExit(f"unknown post {args.id}")
    db.set_status(con, args.id, "skipped", skip_reason=args.reason)
    print(f"skipped {args.id}: {args.reason}")


def cmd_status(args) -> None:
    con = db.connect()
    total = con.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    print(f"posts: {total}")
    for r in con.execute("SELECT status, COUNT(*) n FROM posts GROUP BY status ORDER BY status"):
        print(f"  {r['status']:<10} {r['n']}")
    for r in con.execute("SELECT type, COUNT(*) n FROM posts GROUP BY type"):
        print(f"  type {r['type']}: {r['n']}")
    reasons = con.execute("SELECT skip_reason, COUNT(*) n FROM posts WHERE status = 'skipped'"
                          " GROUP BY skip_reason ORDER BY n DESC").fetchall()
    if reasons:
        print("skipped by reason:")
        for r in reasons:
            print(f"  {r['n']:>3}  {r['skip_reason']}")
    src = con.execute("SELECT value FROM meta WHERE key = 'sync_source'").fetchone()
    if src:
        print(f"last sync source: {src[0]}")


def main() -> None:
    p = argparse.ArgumentParser(prog="vn", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync", help="list the collection and add new posts")
    for name, help_ in (("fetch", "download media for up to N posts"),
                        ("process", "OCR and transcribe up to N fetched posts"),
                        ("run", "sync + fetch + process")):
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("n", nargs="?", type=int)
    sp = sub.add_parser("pending", help="show processed posts waiting for a note")
    sp.add_argument("n", nargs="?", type=int)
    sp.add_argument("--id", help="show one post (any status)")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--ids", action="store_true", help="print only the ids")
    sp = sub.add_parser("done", help="mark a post as written up")
    sp.add_argument("id")
    sp.add_argument("note_path")
    sp = sub.add_parser("skip", help="skip a post with a reason")
    sp.add_argument("id")
    sp.add_argument("reason")
    sub.add_parser("status", help="counts by status and skip reason")
    args = p.parse_args()

    if args.cmd == "sync":
        from .sync import sync
        sync()
    elif args.cmd == "fetch":
        from .fetch import fetch
        fetch(args.n)
    elif args.cmd == "process":
        from .process import process
        process(args.n)
    elif args.cmd == "run":
        from .fetch import fetch
        from .process import process
        from .sync import sync
        sync()
        fetch(args.n)
        process(args.n)
    else:
        {"pending": cmd_pending, "done": cmd_done, "skip": cmd_skip, "status": cmd_status}[args.cmd](args)


if __name__ == "__main__":
    main()
