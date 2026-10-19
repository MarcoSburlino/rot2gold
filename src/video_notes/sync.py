"""vn sync: list each connection and add new posts.

Sources per connection, in order: anonymously, with Firefox cookies (if its cookies_mode allows),
then URLs pasted into the connection by hand. Every listed post is linked to the connection,
so a post saved in two collections is stored once and linked twice.
"""

import random
import time

from . import db, sources
from .errors import CookiesNeeded, ListingFailed
from .events import echo
from .sources import Access

COOKIE_WORDS = ("cookie", "login", "log in", "private", "firefox")


def short(exc: Exception) -> str:
    return str(exc).splitlines()[0][:200] if str(exc) else type(exc).__name__


def access_for(conn, cookies: bool) -> Access:
    return Access(cookies=cookies, firefox_profile=conn["firefox_profile"])


def list_connection(con, conn, src, report=echo) -> tuple[list[sources.ListedPost], str]:
    """(posts, source used) where source is anonymous | cookies | links."""
    modes = {"auto": (False, True), "always": (True,), "never": (False,)}[conn["cookies_mode"]]
    errors = []
    for cookies in modes:
        label = "cookies" if cookies else "anonymous"
        try:
            return src.list_posts(conn["url"], access_for(conn, cookies)), label
        except Exception as exc:
            errors.append(short(exc))
            report(f"{conn['name']}: listing {'with Firefox cookies' if cookies else 'anonymously'} failed: {short(exc)}",
                   level="warn")
    links = [r[0] for r in con.execute("SELECT url FROM connection_links WHERE connection_id = ?", (conn["id"],))]
    posts = [p for p in map(src.parse_post_url, links) if p]
    if posts:
        return posts, "links"
    detail = "; ".join(errors)
    if conn["cookies_mode"] == "never" or any(w in detail.lower() for w in COOKIE_WORDS):
        raise CookiesNeeded(f"Could not list {conn['name']!r}: {detail}")
    raise ListingFailed(f"Could not list {conn['name']!r}: {detail}")


def add_posts(con, conn_id: int, platform: str, posts) -> list[str]:
    """Store listed posts and link them to the connection. Returns the ids that are new."""
    new = []
    for p in posts:
        cur = con.execute(
            "INSERT OR IGNORE INTO posts (id, url, creator, upload_date, platform, added_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (p.id, p.url, p.creator, p.upload_date, platform, db.now(), db.now()),
        )
        if cur.rowcount:
            new.append(p.id)
        con.execute("INSERT OR IGNORE INTO connection_posts VALUES (?, ?, ?)", (conn_id, p.id, db.now()))
    con.commit()
    return new


def detect_types(con, conn, src, access: Access, report=echo) -> None:
    """Fill in type (and missing creator/date) for this connection's new posts that have none yet.

    The flat listing doesn't say whether a post is a slideshow, so each new post's metadata is read once.
    """
    rows = con.execute(
        "SELECT p.id, p.url FROM posts p JOIN connection_posts cp ON cp.post_id = p.id"
        " WHERE cp.connection_id = ? AND p.type IS NULL AND p.status = 'new' ORDER BY p.rowid", (conn["id"],)
    ).fetchall()
    for i, row in enumerate(rows):
        try:
            kind, meta = src.detect_type(row["url"], access)
        except Exception as exc:  # leave type NULL; fetch retries it
            report(f"  {row['id']}: metadata failed: {short(exc)}", post_id=row["id"], level="warn")
            continue
        con.execute(
            "UPDATE posts SET type = ?, creator = COALESCE(creator, ?), upload_date = COALESCE(upload_date, ?),"
            " updated_at = ? WHERE id = ?",
            (kind, meta.get("creator"), meta.get("upload_date"), db.now(), row["id"]),
        )
        con.commit()
        report(f"  {row['id']}: {kind}", post_id=row["id"])
        if i < len(rows) - 1:
            time.sleep(random.uniform(1, 3))


def sync_connection(con, conn, report=echo) -> tuple[int, int]:
    """List one connection. Returns (posts listed, new posts)."""
    src = sources.get(conn["platform"])
    try:
        posts, used = list_connection(con, conn, src, report)
    except Exception as exc:
        con.execute("UPDATE connections SET last_error = ?, updated_at = ? WHERE id = ?",
                    (short(exc), db.now(), conn["id"]))
        con.commit()
        raise
    new = add_posts(con, conn["id"], conn["platform"], posts)
    con.execute("UPDATE connections SET last_synced_at = ?, last_sync_source = ?, last_error = NULL WHERE id = ?",
                (db.now(), used, conn["id"]))
    con.commit()
    report(f"{conn['name']}: {len(posts)} posts listed ({used}), {len(new)} new")
    detect_types(con, conn, src, access_for(conn, used == "cookies"), report)
    return len(posts), len(new)


def connections(con, conn_ids=None) -> list:
    if conn_ids:
        rows = con.execute(f"SELECT * FROM connections WHERE id IN ({db.placeholders(conn_ids)}) ORDER BY id",
                           list(conn_ids)).fetchall()
        missing = set(conn_ids) - {r["id"] for r in rows}
        if missing:
            raise SystemExit(f"unknown connection id(s): {', '.join(map(str, sorted(missing)))} (see `vn conn list`)")
        return rows
    return con.execute("SELECT * FROM connections ORDER BY id").fetchall()


def sync(conn_ids=None, report=echo) -> tuple[int, int]:
    """Sync the given connections (default: all). Returns (posts listed, new posts) in total."""
    con = db.connect()
    conns = connections(con, conn_ids)
    if not conns:
        raise SystemExit("No connections yet. Add one: vn conn add <name> <collection URL>")
    listed = new = 0
    failed = []
    for conn in conns:  # one broken connection doesn't stop the others
        try:
            n_listed, n_new = sync_connection(con, conn, report)
        except (CookiesNeeded, ListingFailed) as exc:
            report(str(exc), level="error")
            failed.append(exc)
            continue
        listed += n_listed
        new += n_new
    if failed and len(failed) == len(conns):
        raise failed[0]
    return listed, new
