"""SQLite state. Each stage reads posts in its input status and commits after every post."""

import sqlite3
from datetime import datetime, timezone

from .config import DATA, DB_PATH

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


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)
    return con


def set_status(con, post_id: str, status: str, **fields) -> None:
    fields["status"] = status
    fields["updated_at"] = now()
    cols = ", ".join(f"{k} = ?" for k in fields)
    con.execute(f"UPDATE posts SET {cols} WHERE id = ?", [*fields.values(), post_id])
    con.commit()


def set_meta(con, key: str, value: str) -> None:
    con.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))
    con.commit()
