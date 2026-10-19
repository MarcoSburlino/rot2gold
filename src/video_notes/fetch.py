"""vn fetch: download media for new posts.

Video: download at a modest resolution, keep the frame at 0.5 s and 16 kHz mono audio, delete the video.
Slideshow: download every image in order (no audio).
"""

import random
import time

from . import db, sources
from .config import ROOT, load, media_dir
from .errors import Blocked
from .events import echo
from .sources import Access
from .sync import short

MAX_ATTEMPTS = 3          # a post that fails this often is skipped with the error as reason
MAX_CONSECUTIVE_FAILS = 5  # this many in a row looks like a block: stop the run


def access_for_post(con, post_id: str) -> Access:
    """Use cookies for a post if any connection it belongs to needed them to list."""
    rows = con.execute(
        "SELECT c.cookies_mode, c.last_sync_source, c.firefox_profile FROM connections c"
        " JOIN connection_posts cp ON cp.connection_id = c.id WHERE cp.post_id = ?", (post_id,)
    ).fetchall()
    for r in rows:
        if r["cookies_mode"] == "always" or r["last_sync_source"] == "cookies":
            return Access(cookies=True, firefox_profile=r["firefox_profile"])
    return Access()


def fetch(limit: int | None = None, ids=None, report=echo) -> int:
    """Download up to `limit` new posts (only those in `ids`, if given). Returns how many were fetched."""
    cfg = load()
    con = db.connect()
    sql, args = "SELECT * FROM posts WHERE status = 'new'", []
    if ids is not None:
        if not ids:
            return 0
        sql += f" AND id IN ({db.placeholders(ids)})"
        args += list(ids)
    posts = con.execute(sql + " ORDER BY rowid LIMIT ?", [*args, limit or -1]).fetchall()
    fails = done = 0
    for i, post in enumerate(posts):
        if i:
            time.sleep(random.uniform(cfg["fetch"]["delay_min"], cfg["fetch"]["delay_max"]))
        try:
            src = sources.get(post["platform"])
            access = access_for_post(con, post["id"])
            kind = post["type"]
            if kind is None:  # sync couldn't read its metadata: try again now
                kind = src.detect_type(post["url"], access)[0]
            images = src.fetch(post["id"], post["url"], kind, media_dir(post["id"]), cfg, access)
            con.execute("DELETE FROM images WHERE post_id = ?", (post["id"],))
            con.executemany("INSERT INTO images (post_id, idx, kind, path) VALUES (?, ?, ?, ?)",
                            [(post["id"], 0 if k == "frame" else n, k, str(p.relative_to(ROOT)))
                             for n, (k, p) in enumerate(images, start=1)])
            db.set_status(con, post["id"], "fetched", type=kind, last_error=None)
            report(f"fetched {post['id']} ({kind})", post_id=post["id"])
            done += 1
            fails = 0
        except Exception as exc:
            con.rollback()
            attempts = post["fetch_attempts"] + 1
            err = short(exc)
            if attempts >= MAX_ATTEMPTS:
                db.set_status(con, post["id"], "skipped", skip_reason=f"fetch failed: {err}",
                              fetch_attempts=attempts, last_error=err)
                report(f"skipped {post['id']}: fetch failed {attempts} times: {err}", post_id=post["id"], level="warn")
            else:
                db.set_status(con, post["id"], "new", fetch_attempts=attempts, last_error=err)
                report(f"failed {post['id']} (attempt {attempts}): {err}", post_id=post["id"], level="warn")
            fails += 1
            if fails >= MAX_CONSECUTIVE_FAILS:
                raise Blocked(f"{fails} downloads failed in a row; last error: {err}") from None
    return done
