"""vn sync: list the collection and add new posts.

Sources, in order: yt-dlp anonymously, yt-dlp with Firefox cookies, data/links.txt.
Only id, URL, creator, upload date and type are stored: never captions, hashtags or comments.
"""

import random
import re
import time
from datetime import datetime, timezone

import yt_dlp

from . import db
from .config import LINKS, load

URL_RE = re.compile(r"tiktok\.com/@([^/?#]+)/(?:video|photo)/(\d+)")


def ydl_opts(cookies: bool = False, **extra) -> dict:
    opts = {"quiet": True, "no_warnings": True, "noprogress": True}
    if cookies:
        opts["cookiesfrombrowser"] = ("firefox",)
    opts.update(extra)
    return opts


def list_with_ytdlp(url: str, cookies: bool) -> list[dict]:
    with yt_dlp.YoutubeDL(ydl_opts(cookies, extract_flat="in_playlist")) as ydl:
        info = ydl.extract_info(url, download=False)
    posts = []
    for e in info.get("entries") or []:
        if not e or not e.get("id"):
            continue
        m = URL_RE.search(e.get("url") or "")
        posts.append({
            "id": e["id"],
            "url": e.get("url") or e.get("webpage_url"),
            "creator": e.get("uploader") or (m.group(1) if m else None),
            "upload_date": to_date(e.get("timestamp")),
        })
    if not posts:
        raise RuntimeError("yt-dlp returned an empty collection")
    return posts


def list_from_links() -> list[dict]:
    if not LINKS.exists():
        return []
    posts = []
    for line in LINKS.read_text().splitlines():
        m = URL_RE.search(line)
        if m:
            posts.append({"id": m.group(2), "url": line.strip(), "creator": m.group(1), "upload_date": None})
    return posts


def to_date(ts) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%d")


def post_info(url: str, cookies: bool = False) -> dict:
    """Full metadata for one post (no download)."""
    with yt_dlp.YoutubeDL(ydl_opts(cookies)) as ydl:
        return ydl.extract_info(url, download=False)


def is_slideshow(info: dict) -> bool:
    # TikTok photo posts expose only their background audio as a format.
    formats = info.get("formats") or []
    return bool(formats) and all((f.get("vcodec") in (None, "none")) for f in formats)


def detect_type(con, cookies: bool) -> None:
    """Fill in type (and missing creator/date) for posts that don't have one yet."""
    rows = con.execute("SELECT id, url FROM posts WHERE type IS NULL AND status = 'new'").fetchall()
    for i, row in enumerate(rows):
        try:
            info = post_info(row["url"], cookies)
        except Exception as exc:  # leave type NULL; fetch retries it
            print(f"  {row['id']}: metadata failed: {short(exc)}")
            continue
        con.execute(
            "UPDATE posts SET type = ?, creator = COALESCE(creator, ?), upload_date = COALESCE(upload_date, ?),"
            " updated_at = ? WHERE id = ?",
            ("slideshow" if is_slideshow(info) else "video", info.get("uploader"),
             to_date(info.get("timestamp")), db.now(), row["id"]),
        )
        con.commit()
        print(f"  {row['id']}: {'slideshow' if is_slideshow(info) else 'video'}")
        if i < len(rows) - 1:
            time.sleep(random.uniform(1, 3))


def short(exc: Exception) -> str:
    return str(exc).splitlines()[0][:200] if str(exc) else type(exc).__name__


def sync() -> None:
    url = load()["collection_url"]
    con = db.connect()
    posts, source = None, None
    for cookies in (False, True):
        label = "yt-dlp + firefox cookies" if cookies else "yt-dlp anonymous"
        try:
            posts, source = list_with_ytdlp(url, cookies), label
            break
        except Exception as exc:
            print(f"{label} failed: {short(exc)}")
    if posts is None:
        posts, source = list_from_links(), "data/links.txt"
        if not posts:
            raise SystemExit("Could not list the collection. Put one post URL per line in data/links.txt and rerun.")
    db.set_meta(con, "sync_source", source)
    db.set_meta(con, "cookies", "1" if source.endswith("cookies") else "0")

    new = 0
    for p in posts:
        cur = con.execute(
            "INSERT OR IGNORE INTO posts (id, url, creator, upload_date, added_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (p["id"], p["url"], p["creator"], p["upload_date"], db.now(), db.now()),
        )
        new += cur.rowcount
    con.commit()
    print(f"sync: {len(posts)} posts in the collection via {source}, {new} new")
    detect_type(con, cookies=source.endswith("cookies"))
