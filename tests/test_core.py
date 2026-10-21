"""Tests for the app's core: migration, lock, connections, brain commits, claude stream parsing.

Everything runs in temporary folders; the real database and brain are never touched.
"""

import sqlite3
import subprocess

import pytest

from rot2gold import brain, connections, db, lock, sync
from rot2gold.ai import claude_cli
from rot2gold.errors import LockHeld
from rot2gold.sources import ListedPost, get

URL = "https://www.tiktok.com/@someone/collection/Material-7000000000000000001"
URL2 = "https://www.tiktok.com/@someone/collection/Ideas-1111111111111111111"


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "load", lambda: {})
    monkeypatch.setattr(db, "LINKS", tmp_path / "links.txt")
    return db.connect(tmp_path / "r2g.sqlite")


def test_migration_from_v1(tmp_path, monkeypatch):
    path = tmp_path / "r2g.sqlite"
    old = sqlite3.connect(path)
    old.executescript(db.SCHEMA)
    for i in range(3):
        old.execute("INSERT INTO posts (id, url, status, added_at, updated_at) VALUES (?, ?, 'done', ?, ?)",
                    (str(i), f"https://www.tiktok.com/@a/video/{i}", f"2026-10-14T22:0{i}:00+00:00", "x"))
    old.execute("INSERT INTO meta VALUES ('sync_source', 'yt-dlp anonymous'), ('cookies', '0')")
    old.commit()
    old.close()
    monkeypatch.setattr(db, "load", lambda: {"collection_url": URL})
    monkeypatch.setattr(db, "LINKS", tmp_path / "links.txt")

    con = db.connect(path)
    assert con.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    conn = con.execute("SELECT * FROM connections").fetchone()
    assert (conn["name"], conn["url"], conn["cookies_mode"], conn["last_sync_source"]) == ("Material", URL, "auto", "anonymous")
    assert conn["last_synced_at"] == "2026-10-14T22:02:00+00:00"
    assert con.execute("SELECT COUNT(*) FROM connection_posts").fetchone()[0] == 3
    assert {"platform", "ideas_checked_at"} <= db.columns(con, "posts")
    assert {"kind", "ideas_created", "ideas_updated"} <= db.columns(con, "runs")
    backup = sqlite3.connect(tmp_path / "r2g.sqlite.bak-v1")
    assert backup.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 3
    assert backup.execute("PRAGMA user_version").fetchone()[0] == 0
    db.connect(path)  # a second start changes nothing
    assert con.execute("SELECT COUNT(*) FROM connections").fetchone()[0] == 1


def test_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(lock, "DATA", tmp_path)
    monkeypatch.setattr(lock, "LOCK_PATH", tmp_path / "r2g.lock")
    assert lock.holder() is None
    with lock.PipelineLock("app", "r2g extract") as held:
        held.update(run_id=7)
        assert lock.holder()["run_id"] == 7
        with pytest.raises(LockHeld, match="an app run"):
            with lock.PipelineLock("terminal", "r2g run"):
                pass
    assert lock.holder() is None


def test_post_in_two_connections_is_stored_once(fresh):
    a = connections.add(fresh, "tiktok", URL + "?is_from_webapp=1")
    b = connections.add(fresh, "tiktok", URL2)
    assert connections.get(fresh, a)["url"] == URL and connections.get(fresh, a)["name"] == "Material"
    shared = ListedPost("100", "https://www.tiktok.com/@x/video/100", "x")
    assert sync.add_posts(fresh, a, "tiktok", [shared, ListedPost("101", "u101")]) == ["100", "101"]
    assert sync.add_posts(fresh, b, "tiktok", [shared, ListedPost("102", "u102")]) == ["102"]
    assert fresh.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 3
    assert db.connection_post_ids(fresh, [a]) == ["100", "101"]
    assert db.connection_post_ids(fresh, [a, b], "new") == ["100", "101", "102"]
    assert connections.only_here(fresh, a) == 1
    connections.delete(fresh, b)
    assert fresh.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 3  # posts stay
    assert db.connection_post_ids(fresh, [b]) == []
    with pytest.raises(ValueError, match="already exists"):
        connections.add(fresh, "tiktok", URL)


def test_links_fallback_keeps_only_post_urls(fresh):
    cid = connections.add(fresh, "tiktok", URL)
    n = connections.set_links(fresh, cid, "https://www.tiktok.com/@a/video/1\nnot a url\nhttps://www.tiktok.com/@b/photo/2\n")
    assert n == 2 and len(connections.links(fresh, cid)) == 2


def test_tiktok_urls():
    src = get("tiktok")
    with pytest.raises(ValueError):
        src.validate_url("https://www.tiktok.com/@a/video/123")
    assert src.parse_post_url("https://www.tiktok.com/@abc/photo/42").id == "42"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    def git(*a):
        subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)
    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    for p in ("Resources/commonplace/quotes.md", "Projects/other.md", "Projects/dirty.md", "index.md"):
        (tmp_path / p).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / p).write_text("v1\n")
    git("add", "-A")
    git("commit", "-q", "-m", "init")
    monkeypatch.setattr(brain, "brain_dir", lambda cfg=None: tmp_path)
    return tmp_path


def test_brain_commits_only_what_the_batch_changed(repo):
    (repo / "Projects/dirty.md").write_text("The user's unsaved edit\n")  # dirty before the batch
    before = brain.snapshot()
    (repo / "Resources/commonplace/quotes.md").write_text("v2\n")
    (repo / "Resources/commonplace/videos").mkdir()
    (repo / "Resources/commonplace/videos/video-new.md").write_text("note\n")
    (repo / "Projects/other.md").write_text("changed by someone else\n")
    (repo / "index.md").write_text("v2\n")
    paths = brain.changed_since(before, brain.note_paths() + brain.extra_paths())
    assert paths == ["Resources/commonplace/quotes.md", "Resources/commonplace/videos/video-new.md", "index.md"]
    sha = brain.commit(paths, "agent: test")
    assert sha
    left = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True).stdout
    assert "Projects/other.md" in left and "Projects/dirty.md" in left and "commonplace" not in left
    assert brain.commit([], "agent: nothing") is None


def test_claude_stream_parsing():
    res, lines = claude_cli.Result(), []
    events = [
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "r2g done 1 Resources/commonplace/videos/video-a.md"}},
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
            {"type": "tool_use", "name": "WebSearch", "input": {"query": "Einstein quote"}}]}},
        {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed", "unifiedWindows": {"five_hour": {"utilization": 0.4}}}},
        {"type": "result", "subtype": "success", "is_error": False, "result": "{}", "structured_output": {"posts": []},
         "num_turns": 5, "duration_ms": 60000, "total_cost_usd": 1.5,
         "usage": {"input_tokens": 3, "output_tokens": 2000, "cache_read_input_tokens": 900000, "cache_creation_input_tokens": 50000}},
    ]
    for ev in events:
        claude_cli.parse_event(ev, res, lines.append)
    assert lines == ["r2g done 1 Resources/commonplace/videos/video-a.md", "search: Einstein quote"]
    assert res.ok and not res.limited and res.structured == {"posts": []}
    assert res.usage["cache_read"] == 900000 and res.cost_usd == 1.5 and res.plan["unifiedWindows"]["five_hour"]["utilization"] == 0.4

    limited = claude_cli.Result()
    claude_cli.parse_event({"type": "rate_limit_event", "rate_limit_info": {"status": "rejected"}}, limited, lines.append)
    assert limited.limited


def test_run_log_never_stops_a_run(fresh, tmp_path, monkeypatch, capsys):
    """Run 1 (2026-10-19) died: process.py reported while its own write was open, and the log write
    waited for it forever. A log line must now give up after 2 s and the run carry on."""
    import time
    from rot2gold.events import Reporter
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "r2g.sqlite")
    fresh.execute("INSERT INTO runs (origin, started_at) VALUES ('terminal', 'x')")
    fresh.commit()
    report = Reporter(1, quiet=True)
    other = db.connect(tmp_path / "r2g.sqlite")
    other.execute("BEGIN IMMEDIATE")  # another connection is mid-write
    other.execute("INSERT INTO meta VALUES ('k', 'v')")
    t0 = time.time()
    report("transcribed 1")  # must not raise
    assert time.time() - t0 < 5
    assert "transcribed 1" in capsys.readouterr().out
    other.commit()
    report("next line")
    assert fresh.execute("SELECT message FROM run_events").fetchall()[-1][0] == "next line"


def test_note_rendering(tmp_path):
    from rot2gold import notefile
    path = tmp_path / "video-x.md"
    path.write_text('---\ndescription: "A test note"\ntags:\n  - tiktok\n---\n\n# The Title\n\n'
                    '> [!note] AI-processed note.\n\n## Content\n\n<script>alert(1)</script> and [[video-y]], '
                    '[[hejdansk|the app]], [[missing-note]] and [a link](https://example.com).\n')
    note = notefile.read(path)
    assert note.title == "The Title" and note.meta["description"] == "A test note"
    assert "# The Title" not in note.body
    links = {"video-y": "/videos/1", "hejdansk": "obsidian://open?path=x"}
    out = notefile.render(note.body, links.get)
    assert "<script>" not in out and "&lt;script&gt;" in out  # raw HTML shown as text, never run
    assert '<a href="/videos/1">video-y</a>' in out
    assert '<a href="obsidian://open?path=x">the app</a>' in out
    assert "missing-note" in out and "[[missing-note]]" not in out
    assert 'class="callout callout-note"' in out
    assert 'target="_blank" rel="noreferrer" href="https://example.com"' in out
    assert notefile.read(path, head_only=True).title == "The Title"
