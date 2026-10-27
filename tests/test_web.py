"""The redesigned pages use temporary database, notes, and media only."""

import asyncio
import json
import httpx
import pytest

from rot2gold import brain, db, ideas, notefile, settings
from rot2gold.sources import firefox
from rot2gold.paths import RESOURCES
from rot2gold.web import app as web


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
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "r2g.sqlite")
    monkeypatch.setattr(db, "LINKS", tmp_path / "none")
    monkeypatch.setattr(db, "load", lambda: {})
    monkeypatch.setattr(brain, "brain_dir", lambda cfg=None: vault)
    monkeypatch.setattr(notefile, "brain_dir", lambda cfg=None: vault)
    monkeypatch.setattr(ideas, "brain_dir", lambda cfg=None: vault)
    monkeypatch.setattr(ideas, "DATA", tmp_path)
    monkeypatch.setattr(web, "DATA", tmp_path)
    monkeypatch.setattr(web, "brain_dir", lambda cfg=None: vault)
    monkeypatch.setattr(web.lock, "DATA", tmp_path)
    monkeypatch.setattr(web.lock, "LOCK_PATH", tmp_path / "r2g.lock")
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
            for path in ("/gold", "/gold/idea-one", "/videos", "/videos?conn=1&status=done", "/videos/101",
                         "/runs", "/runs?conn=1", "/runs?kind=ideas", "/runs/1", "/settings",
                         "/settings/panel", "/ideas/preview/5"):
                response = await client.get(path)
                assert response.status_code == 200, (path, response.text[:500])
            home = await client.get("/", follow_redirects=False)
            assert home.status_code == 303 and home.headers["location"] == "/gold"
            # The pages before Gold still work: they redirect.
            for old, new in (("/ideas", "/gold"), ("/learnings", "/gold?kind=learning"), ("/events", "/gold?kind=event"),
                             ("/ideas/idea-one", "/gold/idea-one"), ("/learnings/learning-x", "/gold/learning-x")):
                moved = await client.get(old, follow_redirects=False)
                assert moved.status_code == 303 and moved.headers["location"] == new, old
            panel = (await client.get("/settings/panel")).text
            assert "<html" not in panel.lower() and "stored-secret-do-not-render" not in panel
            detail = (await client.get("/gold/idea-one")).text
            assert 'aria-current="true"' in detail
            assert 'href="/videos/101"' in detail and '/media/101/frame.jpg' in detail
            assert "Gold from this video" in (await client.get("/videos/101")).text
            filtered = (await client.get("/runs?conn=1")).text
            assert 'href="/runs/1"' in filtered and 'href="/runs/3"' in filtered
            assert 'href="/runs/2"' not in filtered
            values = {f"{f['section']}.{f['key']}": str(web.load()[f['section']].get(f['key']) or "") for f in settings.EDITABLE}
            saved = await client.post("/settings", data=values, headers={"Referer": "http://127.0.0.1:8740/videos?conn=1"}, follow_redirects=False)
            assert saved.status_code == 303
            assert saved.headers["location"].startswith("/videos?")
            assert "settings=general" in saved.headers["location"] and "msg=" in saved.headers["location"]
            denied = await client.post("/extract", data={"conn": "1"}, headers={"Origin": "https://elsewhere.example"})
            assert denied.status_code == 403
    asyncio.run(check())


def test_actions_return_to_the_page_they_came_from(sample, monkeypatch):
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

            started = []
            monkeypatch.setattr(web, "spawn_run", lambda request, cmd, label: started.append(cmd) or web.back("/runs/1"))
            everything = await client.post("/extract", data={}, headers=here, follow_redirects=False)
            assert everything.headers["location"] == "/runs/1"
            assert started[-1][started[-1].index("--conn") + 1] == "1,11"  # nothing picked: every collection

            deleted = await client.post("/connections/11/delete", headers={**here, "Referer": "http://127.0.0.1:8740/videos?conn=11"},
                                        follow_redirects=False)
            assert deleted.headers["location"].startswith("/videos") and "conn=" not in deleted.headers["location"]

            elsewhere = await client.post("/connections", data={"platform": "tiktok", "url": "x"},
                                          headers={"Origin": "http://127.0.0.1:8740", "Referer": "http://evil.example/videos"},
                                          follow_redirects=False)
            assert elsewhere.headers["location"].startswith("/gold")  # never redirect to another site's path

            hidden = await client.get("/gold/idea-one?status=kept")  # idea-one is "new", so the filter hides it
            assert hidden.status_code == 200 and "Try this idea" in hidden.text

            missing = await client.get("/gold/idea-gone", follow_redirects=False)
            assert missing.status_code == 303 and "err=" in missing.headers["location"]

            undo = await client.post("/runs/1/undo", headers=here, follow_redirects=False)
            assert undo.headers["location"].startswith("/runs/1?") and "err=" in undo.headers["location"]

            page = (await client.get("/gold?msg=Saved")).text
            assert 'data-msg=""' in page  # an ordinary message never leaks into the Settings card
    asyncio.run(check())


def test_simple_pages(sample):
    """The 2026-10-20 simplification: plain History, one Extract button, chips only for what exists."""
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web.app), base_url="http://127.0.0.1:8740") as client:
            ideas_page = (await client.get("/gold")).text
            assert "Extract new videos" in ideas_page and 'type="checkbox" name="conn"' not in ideas_page
            assert "Trying" not in ideas_page  # no idea is "trying", so there is no chip for it
            assert 'aria-label="Filter by status"' not in ideas_page  # everything is "new": nothing to pick
            assert "1 note hasn" in ideas_page and "checked for gold yet" in ideas_page and "Check them" in ideas_page  # video-one is unchecked
            history = (await client.get("/runs")).text
            assert "Extract · Collection 1" in history and "No new notes, no new ideas, learnings or events." in history
            run = (await client.get("/runs/2")).text
            assert "Extract · Collection 11" in run and "<summary" in run
            panel = (await client.get("/settings/panel")).text
            assert 'id="tab-general"' in panel and 'id="tab-key"' not in panel and "Advanced" in panel
    asyncio.run(check())


def test_delete_an_idea_with_its_videos_and_undo_it(sample, monkeypatch):
    """Deleting an idea removes its file and, if asked, the notes of videos no other idea uses;
    the videos stay as skipped so Extract won't redo them, and Undo brings everything back."""
    import subprocess
    vault = sample
    videos = vault / "Resources/commonplace/videos"
    (videos / "video-two.md").write_text('---\ndescription: Shared\n---\n# Shared video\n')
    (vault / "Inbox/ideas/idea-one.md").write_text((vault / "Inbox/ideas/idea-one.md").read_text().replace(
        'sources:\n  - "[[video-one]]"', 'sources:\n  - "[[video-one]]"\n  - "[[video-two]]"'))
    (vault / "Inbox/ideas/idea-two.md").write_text(
        '---\ndescription: Another\nstatus: new\nsources:\n  - "[[video-two]]"\nsupport: 1\n---\n# Keep this idea\n\n'
        '## Related ideas\n\n- [[idea-one]]\n')
    (vault / "Resources/commonplace/commonplace.md").write_text(
        '## Posts by theme\n### Useful\n- [[video-one]] — one\n- [[video-two]] — two\n')
    con = web.db.connect()
    con.execute("INSERT INTO posts (id, url, status, note_path, added_at, updated_at) VALUES ('102', 'https://example.com/2',"
                " 'done', 'Resources/commonplace/videos/video-two.md', '2026-10-19', '2026-10-19')")
    con.commit()
    for args in (("init", "-q"), ("config", "user.email", "t@t"), ("config", "user.name", "t"), ("add", "-A"), ("commit", "-q", "-m", "init")):
        subprocess.run(["git", "-C", str(vault), *args], check=True, capture_output=True)
    monkeypatch.setattr(brain, "run_after_write", lambda cfg=None: None)

    found = web.delete.plan(con, "idea-one")
    assert [v["name"] for v in found["videos"]] == ["video-one"]  # video-two also supports idea-two: kept
    assert found["kept"][0]["other_idea"] == "Keep this idea"

    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web.app), base_url="http://127.0.0.1:8740") as client:
            here = {"Origin": "http://127.0.0.1:8740", "Referer": "http://127.0.0.1:8740/gold/idea-one"}
            page = (await client.get("/gold/idea-one")).text
            assert 'id="delete-idea"' in page and "Also delete its video" in page
            assert '<span class="support">2 videos</span>' in page and "from" not in page.split('class="support"')[1][:80]
            assert 'name="then" value="idea-two"' in page  # the row next to it opens after the delete
            done = await client.post("/gold/idea-one/delete?status=new", data={"with_videos": "1", "then": "idea-two"},
                                     headers=here, follow_redirects=False)
            assert done.headers["location"].startswith("/gold/idea-two?status=new&msg=")  # same list, same filter
            assert not (vault / "Inbox/ideas/idea-one.md").exists() and not (videos / "video-one.md").exists()
            assert (videos / "video-two.md").exists()
            assert "[[idea-one]]" not in (vault / "Inbox/ideas/idea-two.md").read_text()
            assert "video-one" not in (vault / "Resources/commonplace/commonplace.md").read_text()
            assert con.execute("SELECT status FROM posts WHERE id = '101'").fetchone()[0] == "skipped"
            assert subprocess.run(["git", "-C", str(vault), "status", "--porcelain"], capture_output=True, text=True).stdout == ""
            run_id = con.execute("SELECT id FROM runs WHERE kind = 'delete'").fetchone()[0]
            history = (await client.get("/runs")).text
            assert "Deleted an idea" in history and "Idea deleted with 1 video." in history
            undone = await client.post(f"/runs/{run_id}/undo", headers=here, follow_redirects=False)
            assert "err=" not in undone.headers["location"]
            assert (vault / "Inbox/ideas/idea-one.md").exists() and (videos / "video-one.md").exists()
            assert con.execute("SELECT status FROM posts WHERE id = '101'").fetchone()[0] == "done"
    asyncio.run(check())


def test_ideas_prompt_lists_every_existing_idea(sample):
    """The ideas pass compares each new video with all existing ideas before creating one."""
    text = ideas.catalog(ideas.list_ideas())
    assert "idea-one.md · Try this idea · A useful idea · new · video-one" in text
    assert "{{existing}}" in (RESOURCES / "prompts/ideas.md").read_text()


def test_learnings_page_video_rail_and_delete(sample, monkeypatch):
    """Learnings get their own page and ⋯ menu; a video a learning uses is never deleted with an idea."""
    import subprocess
    vault = sample
    (vault / "Inbox/learnings").mkdir()
    (vault / "Inbox/learnings/learning-one.md").write_text(
        '---\ndescription: What the video taught\nstatus: new\nupdated: 2026-10-20\n'
        'sources:\n  - "[[video-one]]"\nsupport: 1\n---\n# Explaining shows the gaps\n\n## Use it\n\n- [[idea-one]]\n')
    (vault / "Inbox/ideas/idea-one.md").write_text((vault / "Inbox/ideas/idea-one.md").read_text()
                                                   + "\n## Learnings behind it\n\n- [[learning-one]]\n")
    for args in (("init", "-q"), ("config", "user.email", "t@t"), ("config", "user.name", "t"), ("add", "-A"), ("commit", "-q", "-m", "init")):
        subprocess.run(["git", "-C", str(vault), *args], check=True, capture_output=True)
    monkeypatch.setattr(brain, "run_after_write", lambda cfg=None: None)
    con = web.db.connect()
    found = web.delete.plan(con, "idea-one")
    assert found["videos"] == [] and found["kept"][0]["other_idea"] == "Explaining shows the gaps"

    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web.app), base_url="http://127.0.0.1:8740") as client:
            listing = (await client.get("/gold?kind=learning")).text
            assert "<h1>Gold</h1>" in listing and "Explaining shows the gaps" in listing
            assert 'href="/gold/learning-one?kind=learning"' in listing and "Delete learning…" in listing
            assert "Try this idea" not in listing.split('class="list-pane"')[1].split("</section>")[0]
            assert "1 note hasn" in listing and "checked for gold yet" in listing
            assert 'href="/gold" aria-current="page"' in listing
            assert (await client.get("/gold/learning-one")).status_code == 200
            assert (await client.get("/gold/notes-one")).status_code == 404
            assert (await client.get("/gold/learning-missing", follow_redirects=False)).status_code == 303
            video = (await client.get("/videos/101")).text
            assert "Gold from this video" in video and 'href="/gold/learning-one"' in video
            here = {"Origin": "http://127.0.0.1:8740", "Referer": "http://127.0.0.1:8740/gold/learning-one"}
            assert (await client.post("/gold/notes-one/delete", headers=here)).status_code == 404
            done = await client.post("/gold/learning-one/delete", headers=here, follow_redirects=False)
            assert done.headers["location"].startswith("/gold?msg=")
            assert not (vault / "Inbox/learnings/learning-one.md").exists()
            assert "[[learning-one]]" not in (vault / "Inbox/ideas/idea-one.md").read_text()
            history = (await client.get("/runs")).text
            assert "Deleted a learning" in history and "Learning deleted." in history
    asyncio.run(check())


def test_events_page_groups_by_date_and_offers_a_calendar_file(sample, monkeypatch):
    """Events sort into Coming up and Past by their date; only an upcoming dated one gets Add to calendar."""
    import subprocess
    from datetime import date, timedelta
    vault = sample
    soon = (date.today() + timedelta(days=30)).isoformat()
    (vault / "Inbox/events").mkdir()
    (vault / "Inbox/events/event-design-week.md").write_text(
        f'---\ndescription: A design fair\nwhen: {soon}\nwhere: Milan, Italy\nstatus: new\n'
        'sources:\n  - "[[video-one]]"\nsupport: 1\n---\n# Design week\n')
    (vault / "Inbox/events/event-old-strike.md").write_text(
        '---\ndescription: A strike\nwhen: 1983-06\nstatus: new\nsources:\n  - "[[video-one]]"\nsupport: 1\n---\n# Old strike\n')
    for args in (("init", "-q"), ("config", "user.email", "t@t"), ("config", "user.name", "t"), ("add", "-A"), ("commit", "-q", "-m", "init")):
        subprocess.run(["git", "-C", str(vault), *args], check=True, capture_output=True)
    monkeypatch.setattr(brain, "run_after_write", lambda cfg=None: None)
    assert [e["timing"] for e in ideas.list_events()] == ["upcoming", "past"]

    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web.app), base_url="http://127.0.0.1:8740") as client:
            listing = (await client.get("/gold?kind=event")).text
            assert "<h1>Gold</h1>" in listing and 'href="/gold" aria-current="page"' in listing
            assert 'aria-label="Sort"' not in listing  # events keep their date order
            assert listing.index("Coming up") < listing.index("Design week") < listing.index(">Past<") < listing.index("Old strike")
            assert "Milan, Italy" in listing and "Jun 1983" in listing and "Add to calendar" in listing
            past = (await client.get("/gold?kind=event&status=past")).text
            assert "Old strike" in past and "Design week" not in past.split('class="list-pane"')[1]
            assert "Add to calendar" not in (await client.get("/gold/event-old-strike")).text
            ics = await client.get("/gold/event-design-week/calendar.ics")
            assert ics.status_code == 200 and ics.headers["content-type"].startswith("text/calendar")
            assert f"DTSTART;VALUE=DATE:{soon.replace('-', '')}" in ics.text and "LOCATION:Milan\\, Italy" in ics.text
            assert (await client.get("/gold/event-old-strike/calendar.ics")).status_code == 404
            assert (await client.get("/gold/idea-one/calendar.ics")).status_code == 404
            video = (await client.get("/videos/101")).text
            assert "Gold from this video" in video and 'href="/gold/event-design-week"' in video
            here = {"Origin": "http://127.0.0.1:8740", "Referer": "http://127.0.0.1:8740/gold/event-old-strike"}
            done = await client.post("/gold/event-old-strike/delete?kind=event", headers=here, follow_redirects=False)
            assert done.headers["location"].startswith("/gold?kind=event&msg=")
            assert not (vault / "Inbox/events/event-old-strike.md").exists()
            history = (await client.get("/runs")).text
            assert "Deleted an event" in history and "Event deleted." in history
    asyncio.run(check())


def test_sources_label_says_creators_only_when_they_differ():
    """27 videos from 18 creators: support counts creators, the tiles count videos."""
    strip = web.templates.env.get_template("_macros.html").module.source_strip
    tiles = [{"name": f"video-{n}", "title": "t", "kind": "video"} for n in range(27)]
    html = str(strip({"sources": [t["name"] for t in tiles], "source_tiles": tiles, "support": 18}))
    assert "+21" in html and '<span class="support">27 videos</span>' in html and "from 18 creators" in html
    html = str(strip({"sources": ["video-0"], "source_tiles": tiles[:1], "support": 1}))
    assert '<span class="support">1 video</span>' in html and "creator" not in html
    note = [{"name": "some-note", "title": "some-note", "kind": "note"}]
    assert '<span class="support">1 source</span>' in str(strip({"sources": ["some-note"], "source_tiles": note, "support": 1}))


def test_gold_filters_and_sorting(sample):
    """Gold lists ideas, learnings and events together: filter by kind (To try = ideas and learnings
    with a Try it) and status, sort by sources or by date."""
    vault = sample
    (vault / "Resources/commonplace/videos/video-two.md").write_text('---\ncreator: ann\n---\n# Two\n')
    (vault / "Resources/commonplace/videos/video-three.md").write_text('---\ncreator: bob\n---\n# Three\n')
    (vault / "Inbox/learnings").mkdir()
    (vault / "Inbox/learnings/learning-wins.md").write_text(
        '---\ndescription: Wins build confidence\nstatus: trying\nupdated: 2026-10-01\nsources:\n  - "[[video-two]]"\n'
        '  - "[[video-three]]"\n---\n# Confidence grows from your own wins\n\n## Try it\n\n- Keep a list of wins ([[video-two]])\n')
    (vault / "Inbox/learnings/learning-sleep.md").write_text(
        '---\ndescription: Sleep\nstatus: new\nupdated: 2026-10-25\nsources:\n  - "[[video-two]]"\n---\n# Sleep helps memory\n')
    rows = lambda html: html.split('class="list-pane"')[1].split("</section>")[0]

    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=web.app), base_url="http://127.0.0.1:8740") as client:
            everything = (await client.get("/gold")).text
            listed = rows(everything)
            # Most sources first: the learning from two creators, then the rest.
            assert listed.index("Confidence grows") < listed.index("Sleep helps")
            assert listed.index("Confidence grows") < listed.index("Try this idea")
            # Each row says what it is: the learning with a Try it has both badges, the idea only To try.
            wins = listed.split("Confidence grows")[0].rsplit('class="row idea-row"', 1)[1]
            assert "#i-bulb" in wins and 'class="kind kind-try"' in wins
            idea = listed.split("Try this idea")[0].rsplit('class="row idea-row"', 1)[1]
            assert "#i-bulb" not in idea and 'class="kind kind-try"' in idea
            assert 'aria-label="Filter by status"' in everything  # "new" and "trying": two statuses, so chips
            for label in ("All <span", "Learnings <span", "To try <span", "Most sources", "Newest"):
                assert label in everything, label
            newest = rows((await client.get("/gold?sort=date")).text)
            assert newest.index("Sleep helps") < newest.index("Confidence grows")  # updated 25 Oct before 1 Oct
            to_try = rows((await client.get("/gold?kind=try")).text)
            assert "Confidence grows" in to_try and "Try this idea" in to_try and "Sleep helps" not in to_try
            trying = (await client.get("/gold?kind=learning&status=trying")).text
            assert "Confidence grows" in rows(trying) and "Sleep helps" not in rows(trying)
            assert 'href="/gold/learning-wins?kind=learning&amp;status=trying"' in trying
            searched = rows((await client.get("/gold?q=sleep")).text)
            assert "Sleep helps" in searched and "Confidence grows" not in searched
            assert "Nothing matches" in (await client.get("/gold?q=nothing-like-this")).text
            assert (await client.get("/gold?kind=bogus&sort=bogus")).status_code == 200
    asyncio.run(check())
