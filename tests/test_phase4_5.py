"""Phase 4 and 5 checks use temporary state, fake tools and a temporary Git vault."""

import json
import asyncio
import sqlite3
import subprocess
from pathlib import Path

import pytest
import httpx

from video_notes import brain, config, db, downloaders, launcher, notes, settings, undo
from video_notes.ai import claude_cli
from video_notes.errors import BrainError, UsageLimit
from video_notes.sources import firefox
from video_notes.web import app as web


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "load", lambda: {})
    monkeypatch.setattr(db, "LINKS", tmp_path / "no-links")
    return db.connect(tmp_path / "vn.sqlite")


def test_settings_validation_and_overlay(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(settings, "DATA", tmp_path / "data")
    (tmp_path / "config.toml").write_text("[notes]\nmodel = 'sonnet'\nbatch_size = 3\n")
    before = config.load()
    assert before["notes"]["model"] == "sonnet" and before["notes"]["batch_size"] == 3
    errors = settings.save({"notes.batch_size": "21", "ideas.model": "wrong"})
    assert len(errors) == 2 and not settings.path().exists()
    assert settings.save({"notes.batch_size": "7", "notes.max_budget_usd_per_batch": "",
                          "ideas.model": "haiku"}) == []
    saved = config.load()
    assert saved["notes"]["batch_size"] == 7 and saved["notes"]["model"] == "sonnet"
    assert saved["ideas"]["model"] == "haiku" and saved["notes"]["max_budget_usd_per_batch"] is None
    payload = json.loads(settings.path().read_text())
    payload["brain"] = {"path": "/unsafe"}
    payload["notes"]["unknown"] = 2
    settings.path().write_text(json.dumps(payload))
    assert config.load()["brain"]["path"] == "~/Projects/brain"
    assert "unknown" not in config.load()["notes"]


def test_claude_backends_and_key_test(monkeypatch):
    calls = []
    class Input:
        def write(self, value):
            pass
        def close(self):
            pass
    class Proc:
        stdin = Input()
        stdout = [json.dumps({"type": "result", "subtype": "success", "result": "ok",
                              "structured_output": {"ok": True}})]
        returncode = 0
        def wait(self, **kw):
            return 0
    def popen(cmd, **kw):
        calls.append((cmd, kw))
        return Proc()
    monkeypatch.setattr(claude_cli.shutil, "which", lambda x: "/fake/claude")
    monkeypatch.setattr(claude_cli.subprocess, "Popen", popen)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "parent-secret")
    args = dict(schema={"ok": True}, cwd="/tmp", add_dirs=[], model="opus")
    claude_cli.run("prompt", **args)
    claude_cli.run("prompt", **args, backend="api", api_key="child-secret", max_budget_usd=2)
    assert calls[0][0] == [x for x in calls[1][0] if x not in ("--max-budget-usd", "2")]
    assert "--bare" not in calls[1][0]
    assert "ANTHROPIC_API_KEY" not in calls[0][1]["env"]
    assert calls[1][1]["env"]["ANTHROPIC_API_KEY"] == "child-secret"
    result = claude_cli.test_key("child-secret")
    assert result.ok and calls[-1][0][calls[-1][0].index("--model") + 1] == "haiku"
    assert "WebSearch" not in calls[-1][0] and calls[-1][0][-2:] == ["--max-budget-usd", "0.05"]
    assert Path(calls[-1][1]["cwd"]).name.startswith("tmp")


def test_web_local_requests_and_settings_key(tmp_path, monkeypatch, con):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "vn.sqlite")
    monkeypatch.setattr(web.lock, "DATA", tmp_path)
    monkeypatch.setattr(web.lock, "LOCK_PATH", tmp_path / "vn.lock")
    monkeypatch.setattr(web.secrets, "get_api_key", lambda: "top-secret-value")
    monkeypatch.setattr(web.secrets, "has_api_key", lambda: True)
    monkeypatch.setattr(firefox, "profiles", lambda: [])
    monkeypatch.setattr(web.settings, "DATA", tmp_path / "data")
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web.app),
                                     base_url="http://127.0.0.1:8740") as client:
            assert (await client.get("/healthz")).json() == {"app": web.APP_NAME}
            assert "top-secret-value" not in (await client.get("/settings")).text
            assert (await client.get("/healthz", headers={"Host": "evil.example"})).status_code == 400
            assert (await client.post("/settings", data={}, follow_redirects=False)).status_code == 403
            assert (await client.post("/settings", data={}, headers={"Origin": "https://evil.example"})).status_code == 403
            assert (await client.post("/settings", data={}, headers={"Origin": "http://localhost:8740"},
                                      follow_redirects=False)).status_code == 303
            assert (await client.post("/settings", data={}, headers={"Referer": "http://127.0.0.1:8740/settings"},
                                      follow_redirects=False)).status_code == 303
    asyncio.run(check())


def test_v3_to_v4_idempotent(tmp_path, monkeypatch):
    path = tmp_path / "vn.sqlite"
    old = sqlite3.connect(path)
    old.executescript(db.SCHEMA + db.SCHEMA_V2)
    for name, decl in (("kind", "TEXT NOT NULL DEFAULT 'extract'"),
                       ("ideas_created", "INTEGER NOT NULL DEFAULT 0"),
                       ("ideas_updated", "INTEGER NOT NULL DEFAULT 0")):
        old.execute(f"ALTER TABLE runs ADD COLUMN {name} {decl}")
    old.execute("PRAGMA user_version = 3")
    old.commit()
    old.close()
    monkeypatch.setattr(db, "load", lambda: {})
    con = db.connect(path)
    assert "undone_at" in db.columns(con, "runs")
    assert "cost_usd" in db.columns(con, "batches")
    db.connect(path)
    assert con.execute("PRAGMA user_version").fetchone()[0] == 4
    assert not (tmp_path / "vn.sqlite.bak-v1").exists()


def git(root, *args, check=True):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=check)


@pytest.fixture
def vault(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@t")
    git(root, "config", "user.name", "t")
    (root / "Resources/commonplace/videos").mkdir(parents=True)
    (root / "index.md").write_text("index\n")
    git(root, "add", "--", "index.md")
    git(root, "commit", "-q", "-m", "init")
    monkeypatch.setattr(brain, "brain_dir", lambda cfg=None: root)
    monkeypatch.setattr(brain, "brain_index", lambda: None)
    return root


@pytest.mark.parametrize("limited", [False, True])
def test_note_batches_and_undo(vault, con, monkeypatch, limited):
    note = vault / "Resources/commonplace/videos/video-one.md"
    con.execute("INSERT INTO posts (id, url, status, added_at, updated_at) VALUES ('1', 'u', 'processed', 'x', 'x')")
    con.execute("INSERT INTO runs (origin, started_at, status) VALUES ('terminal', 'x', 'ok')")
    con.commit()
    def fake(prompt, **kw):
        note.write_text('---\npost_id: "1"\n---\n# One\n')
        con.execute("UPDATE posts SET status='done', note_path='Resources/commonplace/videos/video-one.md' WHERE id='1'")
        con.commit()
        result = claude_cli.Result(ok=not limited, cost_usd=0.1, turns=2, duration_ms=120000,
                                   plan={"unifiedWindows": {"five_hour": {"utilization": 0.5}}})
        if limited:
            exc = UsageLimit("usage limit")
            exc.result = result
            raise exc
        return result
    monkeypatch.setattr(claude_cli, "run", fake)
    cfg = {"notes": {"batch_size": 5, "model": "opus", "backend": "subscription"},
           "brain": {"path": str(vault)}}
    if limited:
        with pytest.raises(UsageLimit):
            notes.write_notes(con, ["1"], cfg, lambda *a, **kw: None, 1)
    else:
        assert notes.write_notes(con, ["1"], cfg, lambda *a, **kw: None, 1) == (1, 0)
    row = con.execute("SELECT * FROM batches").fetchone()
    assert row["kind"] == "notes" and row["noted"] == "1" and row["five_hour"] == 0.5
    assert row["ok"] == int(not limited)
    result = undo.undo_run(con, 1, lambda *a, **kw: None)
    assert result["reopened"] == ["1"] and not note.exists()
    assert con.execute("SELECT status FROM posts WHERE id='1'").fetchone()[0] == "processed"
    assert con.execute("SELECT undone_at FROM runs WHERE id=1").fetchone()[0]
    assert git(vault, "status", "--porcelain").stdout == ""


def test_undo_refuses_later_and_dirty_edits(vault, con):
    note = vault / "Resources/commonplace/videos/video-one.md"
    note.write_text("one\n")
    git(vault, "add", "--", "Resources/commonplace/videos/video-one.md")
    git(vault, "commit", "-q", "-m", "run")
    first = git(vault, "rev-parse", "HEAD").stdout.strip()
    con.execute("INSERT INTO runs (origin, started_at, status, brain_commits) VALUES ('terminal', 'x', 'ok', ?)", (first,))
    con.commit()
    note.write_text("local edit\n")
    with pytest.raises(ValueError, match="uncommitted"):
        undo.undo_run(con, 1, lambda *a, **kw: None)
    git(vault, "restore", "--", "Resources/commonplace/videos/video-one.md")
    note.write_text("later commit\n")
    git(vault, "add", "--", "Resources/commonplace/videos/video-one.md")
    git(vault, "commit", "-q", "-m", "later")
    with pytest.raises(BrainError, match="Later changes touched"):
        undo.undo_run(con, 1, lambda *a, **kw: None)
    assert note.read_text() == "later commit\n"
    assert git(vault, "status", "--porcelain").stdout == ""


def test_downloader_update_and_launcher(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(downloaders.shutil, "which", lambda name: "/fake/uv" if name == "uv" else None)
    monkeypatch.setattr(downloaders.Path, "is_file", lambda self: True if str(self) == "/fake/uv" else Path.exists(self))
    monkeypatch.setattr(downloaders, "ROOT", tmp_path)
    monkeypatch.setattr(downloaders, "versions", lambda: {"yt-dlp": "2026.01.01", "gallery-dl": "1"})
    class Proc:
        stdout = ["updating\n"]
        returncode = 0
        def wait(self):
            return 0
    monkeypatch.setattr(downloaders.subprocess, "Popen", lambda cmd, **kw: (calls.append(cmd) or Proc()))
    monkeypatch.setattr(downloaders.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0,
                            stdout='{"yt-dlp": "2026.10.19", "gallery-dl": "2"}'))
    lines = []
    assert downloaders.update(lines.append)["gallery-dl"] == "2"
    assert calls[0][1:4] == ["pip", "install", "--python"] and "updating" in lines
    monkeypatch.setattr(launcher.shutil, "which", lambda name: None)
    desktop, icon = launcher.install(home=tmp_path)
    assert desktop.is_file() and icon.is_file() and "Terminal=false" in desktop.read_text()
    assert str(tmp_path / ".local/bin/vn ui") in desktop.read_text()
    launcher.uninstall(home=tmp_path)
    assert not desktop.exists() and not icon.exists()
