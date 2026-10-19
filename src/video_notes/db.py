"""SQLite state. Each stage reads posts in its input status and commits after every post.

Schema v4 adds per-batch usage and run undo state. See docs/app-spec.md.
"""

import sqlite3
from datetime import datetime, timezone

from .config import DATA, DB_PATH, LINKS, load

SCHEMA_VERSION = 4

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    creator TEXT,
    upload_date TEXT,              -- YYYY-MM-DD (UTC)
    type TEXT,                     -- video | slideshow
    status TEXT NOT NULL DEFAULT 'new',  -- new | fetched | processed | done | skipped
    skip_reason TEXT,
    note_path TEXT,
    language TEXT,                 -- detected by Whisper (videos with speech)
    language_prob REAL,
    whisper_model TEXT,
    transcribed INTEGER NOT NULL DEFAULT 0,
    fetch_attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    added_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS images (
    post_id TEXT NOT NULL REFERENCES posts(id),
    idx INTEGER NOT NULL,          -- 0 = video frame, 1.. = slides in order
    kind TEXT NOT NULL,            -- frame | slide
    path TEXT NOT NULL,            -- relative to the project root
    ocr_text TEXT,                 -- NULL until OCR has run
    ocr_conf REAL,                 -- mean word confidence 0-100
    PRIMARY KEY (post_id, idx)
);
CREATE TABLE IF NOT EXISTS segments (
    post_id TEXT NOT NULL REFERENCES posts(id),
    idx INTEGER NOT NULL,
    start REAL NOT NULL,
    end REAL NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (post_id, idx)
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""

SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS connections (
    id INTEGER PRIMARY KEY,
    platform TEXT NOT NULL,        -- key in sources.SOURCES, e.g. tiktok
    name TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    cookies_mode TEXT NOT NULL DEFAULT 'auto',  -- auto | always | never
    firefox_profile TEXT,          -- NULL = let yt-dlp pick the profile
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_synced_at TEXT,
    last_sync_source TEXT,         -- anonymous | cookies | links
    last_error TEXT
);
CREATE TABLE IF NOT EXISTS connection_posts (
    connection_id INTEGER NOT NULL REFERENCES connections(id) ON DELETE CASCADE,
    post_id TEXT NOT NULL REFERENCES posts(id),
    first_seen_at TEXT NOT NULL,
    PRIMARY KEY (connection_id, post_id)
);
CREATE INDEX IF NOT EXISTS connection_posts_post ON connection_posts(post_id);
CREATE TABLE IF NOT EXISTS connection_links (  -- post URLs pasted by hand, used when listing fails
    connection_id INTEGER NOT NULL REFERENCES connections(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    PRIMARY KEY (connection_id, url)
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    origin TEXT NOT NULL,          -- app | terminal
    connection_ids TEXT,           -- comma-separated
    backend TEXT,
    model TEXT,
    pid INTEGER,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',  -- running | ok | stopped | failed | interrupted
    stage TEXT,
    error TEXT,
    posts_listed INTEGER NOT NULL DEFAULT 0,
    posts_fetched INTEGER NOT NULL DEFAULT 0,
    posts_processed INTEGER NOT NULL DEFAULT 0,
    posts_noted INTEGER NOT NULL DEFAULT 0,
    posts_skipped INTEGER NOT NULL DEFAULT 0,
    tokens_in INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    cache_read INTEGER NOT NULL DEFAULT 0,
    cache_write INTEGER NOT NULL DEFAULT 0,
    cost_estimate_usd REAL NOT NULL DEFAULT 0,
    plan_usage TEXT,               -- latest rate_limit_info from claude -p, as JSON
    brain_commits TEXT             -- space-separated commit hashes
);
CREATE TABLE IF NOT EXISTS run_events (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    ts TEXT NOT NULL,
    level TEXT NOT NULL,           -- info | warn | error
    stage TEXT,
    post_id TEXT,
    message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS run_events_run ON run_events(run_id, id);
"""

SCHEMA_V4 = """
CREATE TABLE IF NOT EXISTS batches (
    id INTEGER PRIMARY KEY,
    run_id INTEGER REFERENCES runs(id),
    kind TEXT NOT NULL CHECK (kind IN ('notes', 'ideas', 'apply')),
    n INTEGER NOT NULL,
    post_ids TEXT,
    noted TEXT,
    considered TEXT,
    turns INTEGER,
    duration_ms INTEGER,
    tokens_in INTEGER,
    tokens_out INTEGER,
    cache_read INTEGER,
    cache_write INTEGER,
    cost_usd REAL,
    five_hour REAL,
    ok INTEGER,
    error TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS batches_run ON batches(run_id, id);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path=None) -> sqlite3.Connection:
    """Open the database, creating or migrating it as needed.

    WAL mode lets the app read while a run writes; the busy timeout makes a writer wait
    for another writer instead of failing.
    """
    path = path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA busy_timeout = 30000")
    con.execute("PRAGMA foreign_keys = ON")
    if con.execute("PRAGMA user_version").fetchone()[0] < SCHEMA_VERSION:
        migrate(con, path)
    return con


def columns(con, table: str) -> set[str]:
    return {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}


def migrate(con, path) -> None:
    """Add v2 through v4 fields; back up an existing v1 database only once."""
    version = con.execute("PRAGMA user_version").fetchone()[0]
    con.executescript(SCHEMA)
    has_posts = con.execute("SELECT COUNT(*) FROM posts").fetchone()[0] > 0
    backup = path.with_name(path.name + ".bak-v1")
    if version < 2 and has_posts and not backup.exists():
        with sqlite3.connect(backup) as dst:
            con.backup(dst)
    con.executescript(SCHEMA_V2)
    cols = columns(con, "posts")
    if "platform" not in cols:
        con.execute("ALTER TABLE posts ADD COLUMN platform TEXT NOT NULL DEFAULT 'tiktok'")
    if "ideas_checked_at" not in cols:
        con.execute("ALTER TABLE posts ADD COLUMN ideas_checked_at TEXT")
    run_cols = columns(con, "runs")
    for name, decl in (("kind", "TEXT NOT NULL DEFAULT 'extract'"),
                       ("ideas_created", "INTEGER NOT NULL DEFAULT 0"),
                       ("ideas_updated", "INTEGER NOT NULL DEFAULT 0"),
                       ("undone_at", "TEXT")):
        if name not in run_cols:
            con.execute(f"ALTER TABLE runs ADD COLUMN {name} {decl}")
    con.executescript(SCHEMA_V4)
    # The single collection of v1 becomes the first connection, with every existing post in it.
    url = load().get("collection_url") if version < 2 else None
    if url and not con.execute("SELECT 1 FROM connections").fetchone():
        cookies = (con.execute("SELECT value FROM meta WHERE key = 'cookies'").fetchone() or ["0"])[0] == "1"
        src = (con.execute("SELECT value FROM meta WHERE key = 'sync_source'").fetchone() or [None])[0]
        cur = con.execute(
            "INSERT INTO connections (platform, name, url, cookies_mode, created_at, updated_at,"
            " last_synced_at, last_sync_source) VALUES ('tiktok', ?, ?, ?, ?, ?, ?, ?)",
            (collection_name(url), url, "always" if cookies else "auto", now(), now(),
             con.execute("SELECT MAX(added_at) FROM posts").fetchone()[0] if src else None, {"yt-dlp anonymous": "anonymous", "yt-dlp + firefox cookies": "cookies",
                                      "data/links.txt": "links"}.get(src, src)),
        )
        con.execute("INSERT OR IGNORE INTO connection_posts SELECT ?, id, added_at FROM posts", (cur.lastrowid,))
        if LINKS.exists():
            con.executemany("INSERT OR IGNORE INTO connection_links VALUES (?, ?)",
                            [(cur.lastrowid, line.strip()) for line in LINKS.read_text().splitlines() if line.strip()])
    con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    con.commit()


def add_batch(con, run_id, kind, n, post_ids=(), noted=(), considered=(), res=None, error=None) -> None:
    if run_id is None:
        return
    usage = res.usage if res else {}
    plan = (((res.plan or {}).get("unifiedWindows") or {}).get("five_hour") or {}) if res else {}
    con.execute("INSERT INTO batches (run_id, kind, n, post_ids, noted, considered, turns, duration_ms,"
                " tokens_in, tokens_out, cache_read, cache_write, cost_usd, five_hour, ok, error, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, kind, n, " ".join(post_ids), " ".join(noted), " ".join(considered),
                 res.turns if res else None, res.duration_ms if res else None,
                 usage.get("tokens_in"), usage.get("tokens_out"), usage.get("cache_read"), usage.get("cache_write"),
                 res.cost_usd if res else None, plan.get("utilization"), int(bool(res.ok if res else kind == "apply") and not error),
                 str(error or (res.error if res and not res.ok else ""))[:500] or None, now()))
    con.commit()


def collection_name(url: str) -> str:
    """'…/collection/Material-7000…' → 'Material'."""
    tail = url.rstrip("/").split("/collection/")[-1].split("?")[0]
    return tail.rsplit("-", 1)[0] if "-" in tail else tail or "Collection"


def set_status(con, post_id: str, status: str, **fields) -> None:
    fields["status"] = status
    fields["updated_at"] = now()
    cols = ", ".join(f"{k} = ?" for k in fields)
    con.execute(f"UPDATE posts SET {cols} WHERE id = ?", [*fields.values(), post_id])
    con.commit()


def set_meta(con, key: str, value: str) -> None:
    con.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))
    con.commit()


def placeholders(items) -> str:
    return ",".join("?" * len(items))


def connection_post_ids(con, conn_ids, status: str | None = None) -> list[str]:
    """Ids of posts in any of the given connections, oldest first, optionally with one status."""
    if not conn_ids:
        return []
    sql = (f"SELECT DISTINCT p.id FROM posts p JOIN connection_posts cp ON cp.post_id = p.id"
           f" WHERE cp.connection_id IN ({placeholders(conn_ids)})")
    args = list(conn_ids)
    if status:
        sql += " AND p.status = ?"
        args.append(status)
    return [r[0] for r in con.execute(sql + " ORDER BY p.rowid", args)]


def mark_interrupted_runs(con, running_pid: int | None) -> None:
    """Runs left 'running' by a process that died (e.g. kill -9) are marked interrupted."""
    con.execute("UPDATE runs SET status = 'interrupted', finished_at = COALESCE(finished_at, ?)"
                " WHERE status = 'running' AND (pid IS NOT ? OR ? IS NULL)", (now(), running_pid, running_pid))
    con.commit()
