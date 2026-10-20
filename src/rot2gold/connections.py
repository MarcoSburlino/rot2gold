"""Connections: the collections the pipeline reads. Shared by `r2g conn` and the app."""

import sqlite3

from . import db, sources

COOKIE_MODES = ("auto", "always", "never")
STATUSES = ("new", "fetched", "processed", "done", "skipped")
LABELS = {"new": "listed", "fetched": "fetched", "processed": "processed", "done": "noted", "skipped": "skipped"}


def add(con, platform: str, url: str, name: str = "", cookies_mode: str = "auto") -> int:
    src = sources.get(platform)
    url = src.validate_url(url)
    name = (name or src.default_name(url) or "Collection").strip()
    if cookies_mode not in COOKIE_MODES:
        raise ValueError(f"cookies must be one of {', '.join(COOKIE_MODES)}")
    try:
        cur = con.execute("INSERT INTO connections (platform, name, url, cookies_mode, created_at, updated_at)"
                          " VALUES (?, ?, ?, ?, ?, ?)", (platform, name, url, cookies_mode, db.now(), db.now()))
    except sqlite3.IntegrityError:
        raise ValueError(f"a connection named {name!r} already exists") from None
    con.commit()
    return cur.lastrowid


def get(con, conn_id: int):
    row = con.execute("SELECT * FROM connections WHERE id = ?", (conn_id,)).fetchone()
    if not row:
        raise ValueError(f"no connection with id {conn_id}")
    return row


def update(con, conn_id: int, *, name=None, url=None, cookies_mode=None, firefox_profile=None) -> None:
    row = get(con, conn_id)
    fields = {}
    if name is not None and name.strip():
        fields["name"] = name.strip()
    if url is not None and url.strip():
        fields["url"] = sources.get(row["platform"]).validate_url(url)
    if cookies_mode is not None:
        if cookies_mode not in COOKIE_MODES:
            raise ValueError(f"cookies must be one of {', '.join(COOKIE_MODES)}")
        fields["cookies_mode"] = cookies_mode
    if firefox_profile is not None:
        fields["firefox_profile"] = firefox_profile.strip() or None
    if not fields:
        return
    fields["updated_at"] = db.now()
    try:
        con.execute(f"UPDATE connections SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                    [*fields.values(), conn_id])
    except sqlite3.IntegrityError:
        raise ValueError(f"a connection named {fields.get('name')!r} already exists") from None
    con.commit()


def only_here(con, conn_id: int) -> int:
    """Posts that belong to this connection and no other."""
    return con.execute(
        "SELECT COUNT(*) FROM connection_posts cp WHERE cp.connection_id = ? AND NOT EXISTS"
        " (SELECT 1 FROM connection_posts o WHERE o.post_id = cp.post_id AND o.connection_id != cp.connection_id)",
        (conn_id,)).fetchone()[0]


def delete(con, conn_id: int) -> None:
    """Remove the connection and its links. Posts, media and brain notes stay."""
    get(con, conn_id)
    con.execute("DELETE FROM connection_posts WHERE connection_id = ?", (conn_id,))
    con.execute("DELETE FROM connection_links WHERE connection_id = ?", (conn_id,))
    con.execute("DELETE FROM connections WHERE id = ?", (conn_id,))
    con.commit()


def set_links(con, conn_id: int, text: str) -> int:
    """Replace the hand-pasted post URLs (one per line). Returns how many valid URLs were kept."""
    src = sources.get(get(con, conn_id)["platform"])
    urls = [line.strip() for line in text.splitlines() if src.parse_post_url(line)]
    con.execute("DELETE FROM connection_links WHERE connection_id = ?", (conn_id,))
    con.executemany("INSERT OR IGNORE INTO connection_links VALUES (?, ?)", [(conn_id, u) for u in urls])
    con.commit()
    return len(urls)


def links(con, conn_id: int) -> list[str]:
    return [r[0] for r in con.execute("SELECT url FROM connection_links WHERE connection_id = ?", (conn_id,))]


def counts(con, conn_id: int) -> dict[str, int]:
    c = dict.fromkeys(STATUSES, 0)
    for r in con.execute("SELECT p.status, COUNT(*) n FROM posts p JOIN connection_posts cp ON cp.post_id = p.id"
                         " WHERE cp.connection_id = ? GROUP BY p.status", (conn_id,)):
        c[r["status"]] = r["n"]
    c["total"] = sum(c[s] for s in STATUSES)
    return c


def all_with_counts(con) -> list[dict]:
    return [dict(r) | {"counts": counts(con, r["id"]), "only_here": only_here(con, r["id"])}
            for r in con.execute("SELECT * FROM connections ORDER BY id")]
