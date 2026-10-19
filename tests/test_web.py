"""The redesigned pages use temporary database, notes, and media only."""

import asyncio
import json
import httpx
import pytest

from video_notes import brain, db, ideas, notefile, settings
from video_notes.sources import firefox
from video_notes.web import app as web


@pytest.fixture
def sample(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    note_dir = vault / "Resources/commonplace/videos"
    idea_dir = vault / "Inbox/ideas"
    note_dir.mkdir(parents=True)
    idea_dir.mkdir(parents=True)
    note = note_dir / "video-one.md"
    note.write_text('---\ndescription: A short summary\n---\n# Useful video\nA safe note.\n')
    (idea_dir / "idea-one.md").write_text(
        '---\ndescription: A useful idea\nstatus: new\ncreated: 2026-10-19\nupdated: 2026-10-19\n'
        'sources:\n  - "[[video-one]]"\nsupport: 1\n---\n# Try this idea\nUse [[video-one]].\n')
    (vault / "Resources/commonplace/commonplace.md").write_text(
        '## Posts by theme\n### Useful\n- [[video-one]]\n')
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "vn.sqlite")
    monkeypatch.setattr(db, "LINKS", tmp_path / "none")
    monkeypatch.setattr(db, "load", lambda: {})
    monkeypatch.setattr(brain, "brain_dir", lambda cfg=None: vault)
    monkeypatch.setattr(notefile, "brain_dir", lambda cfg=None: vault)
    monkeypatch.setattr(ideas, "brain_dir", lambda cfg=None: vault)
    monkeypatch.setattr(ideas, "DATA", tmp_path)
    monkeypatch.setattr(web, "DATA", tmp_path)
    monkeypatch.setattr(web, "brain_dir", lambda cfg=None: vault)
    monkeypatch.setattr(web.lock, "DATA", tmp_path)
    monkeypatch.setattr(web.lock, "LOCK_PATH", tmp_path / "vn.lock")
    monkeypatch.setattr(settings, "DATA", tmp_path)
    monkeypatch.setattr(firefox, "profiles", lambda: [])
    monkeypatch.setattr(web.secrets, "has_api_key", lambda: True)
    monkeypatch.setattr(web.secrets, "get_api_key", lambda: "stored-secret-do-not-render")
    monkeypatch.setattr(web.downloaders, "versions", lambda: {"yt-dlp": "1", "gallery-dl": "2", "yt-dlp_age_days": 0})
    con = db.connect()
    for cid in (1, 11):
        con.execute("INSERT INTO connections (id, platform, name, url, created_at, updated_at) VALUES (?, 'tiktok', ?, 'https://example.com', '2026-10-19', '2026-10-19')", (cid, f"Collection {cid}"))
    con.execute("INSERT INTO posts (id, url, status, note_path, creator, type, added_at, updated_at) VALUES ('101', 'https://example.com/video', 'done', ?, 'marco', 'video', '2026-10-19', '2026-10-19')", (str(note.relative_to(vault)),))
    con.execute("INSERT INTO connection_posts VALUES (1, '101', '2026-10-19')")
    con.execute("INSERT INTO images (post_id, idx, kind, path) VALUES ('101', 0, 'frame', 'media/101/frame.jpg')")
    for ids in ("1", "11", "1,11", ""):
        con.execute("INSERT INTO runs (origin, connection_ids, kind, started_at, status) VALUES ('app', ?, ?, '2026-10-19', 'ok')", (ids, "ideas" if not ids else "extract"))
    con.execute("INSERT INTO runs (origin, kind, started_at, status) VALUES ('app', 'ideas-dry-run', '2026-10-19', 'ok')")
    con.commit()
    media = tmp_path / "media/101"
    media.mkdir(parents=True)
    (media / "frame.jpg").write_bytes(b"test image")
    monkeypatch.setattr(web, "MEDIA", tmp_path / "media")
    monkeypatch.setattr(web, "media_dir", lambda post_id: tmp_path / "media" / post_id)
    preview = tmp_path / "ideas-dry-run/run-5"
    preview.mkdir(parents=True)
    (preview / "idea-preview.md").write_text('# Another idea\n')
    (preview / "manifest.json").write_text(json.dumps({"considered": ["101"]}))
    return vault


def test_pages_and_links(sample):
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web.app), base_url="http://127.0.0.1:8740") as client:
            for path in ("/ideas", "/ideas/idea-one", "/videos", "/videos?conn=1&status=done", "/videos/101",
                         "/runs", "/runs?conn=1", "/runs?kind=ideas", "/runs/1", "/settings",
                         "/settings/panel", "/ideas/preview/5"):
                response = await client.get(path)
                assert response.status_code == 200, (path, response.text[:500])
            home = await client.get("/", follow_redirects=False)
            assert home.status_code == 303 and home.headers["location"] == "/ideas"
            panel = (await client.get("/settings/panel")).text
            assert "<html" not in panel.lower() and "stored-secret-do-not-render" not in panel
            detail = (await client.get("/ideas/idea-one")).text
            assert 'aria-current="true"' in detail
            assert 'href="/videos/101"' in detail and '/media/101/frame.jpg' in detail
            assert "Ideas from this video" in (await client.get("/videos/101")).text
            filtered = (await client.get("/runs?conn=1")).text
            assert 'href="/runs/1"' in filtered and 'href="/runs/3"' in filtered
            assert 'href="/runs/2"' not in filtered
            values = {f"{f['section']}.{f['key']}": str(web.load()[f['section']].get(f['key']) or "") for f in settings.EDITABLE}
            saved = await client.post("/settings", data=values, headers={"Referer": "http://127.0.0.1:8740/videos?conn=1"}, follow_redirects=False)
            assert saved.status_code == 303
            assert saved.headers["location"].startswith("/videos?")
            assert "settings=notes" in saved.headers["location"] and "msg=" in saved.headers["location"]
            denied = await client.post("/extract", data={"conn": "1"}, headers={"Origin": "https://elsewhere.example"})
            assert denied.status_code == 403
    asyncio.run(check())


def test_actions_return_to_the_page_they_came_from(sample):
    """Bugs fixed in the 2026-10-19 UI rebuild: actions used to jump back to Ideas, a filtered-out idea
    gave 'Not found', and deleting a collection left its filter in the address."""
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web.app), base_url="http://127.0.0.1:8740") as client:
            here = {"Origin": "http://127.0.0.1:8740", "Referer": "http://127.0.0.1:8740/videos?conn=1&status=done&err=old"}

            bad = await client.post("/connections", data={"platform": "tiktok", "url": "https://example.com/x"},
                                    headers=here, follow_redirects=False)
            location = bad.headers["location"]
            assert location.startswith("/videos?") and "conn=1" in location and "status=done" in location
            assert "err=" in location and "old" not in location  # the stale message is replaced, not repeated

            none = await client.post("/extract", data={}, headers=here, follow_redirects=False)
            assert none.headers["location"].startswith("/videos?") and "err=" in none.headers["location"]

            deleted = await client.post("/connections/11/delete", headers={**here, "Referer": "http://127.0.0.1:8740/videos?conn=11"},
                                        follow_redirects=False)
            assert deleted.headers["location"].startswith("/videos") and "conn=" not in deleted.headers["location"]

            elsewhere = await client.post("/connections", data={"platform": "tiktok", "url": "x"},
                                          headers={"Origin": "http://127.0.0.1:8740", "Referer": "http://evil.example/videos"},
                                          follow_redirects=False)
            assert elsewhere.headers["location"].startswith("/ideas")  # never redirect to another site's path

            hidden = await client.get("/ideas/idea-one?status=kept")  # idea-one is "new", so the filter hides it
            assert hidden.status_code == 200 and "Try this idea" in hidden.text

            missing = await client.get("/ideas/idea-gone", follow_redirects=False)
            assert missing.status_code == 303 and "err=" in missing.headers["location"]

            undo = await client.post("/runs/1/undo", headers=here, follow_redirects=False)
            assert undo.headers["location"].startswith("/runs/1?") and "err=" in undo.headers["location"]

            page = (await client.get("/ideas?msg=Saved")).text
            assert 'data-msg=""' in page  # an ordinary message never leaks into the Settings card
    asyncio.run(check())
