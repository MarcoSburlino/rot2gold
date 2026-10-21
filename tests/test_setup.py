"""Config for other people's machines: the default vault layout, vaults without Git, data-relative paths."""

import sqlite3

import pytest
import tomli_w

from rot2gold import brain, config, db


@pytest.fixture
def plain_vault(tmp_path, monkeypatch):
    """A vault with the default single-folder layout and no Git."""
    path = tmp_path / "config.toml"
    vault = tmp_path / "vault"
    vault.mkdir()
    path.write_text(tomli_w.dumps({"vault": {"path": str(vault)}}))
    monkeypatch.setenv("R2G_CONFIG", str(path))
    return vault


def test_default_layout_keeps_everything_in_one_folder(plain_vault):
    cfg = config.load()
    assert config.is_set_up(cfg) and config.brain_dir(cfg) == plain_vault
    assert brain.note_paths() == ("Rot2Gold/Videos/", "Rot2Gold/Rot2Gold.md", "Rot2Gold/Quotes.md")
    assert brain.idea_paths() == ("Rot2Gold/Ideas/", "Rot2Gold/Learnings/", "Rot2Gold/Events/")
    assert all(p.startswith("Rot2Gold/") for p in brain.note_paths() + brain.idea_paths())


def test_unconfigured_until_a_vault_is_set(tmp_path, monkeypatch):
    monkeypatch.setenv("R2G_CONFIG", str(tmp_path / "missing.toml"))
    assert not config.is_set_up()
    assert config.data_dir() == config.default_data_dir()


def test_without_git_changes_are_found_by_hashing_and_nothing_is_committed(plain_vault):
    assert not brain.uses_git()
    (plain_vault / "Rot2Gold/Videos").mkdir(parents=True)
    (plain_vault / "Rot2Gold/Quotes.md").write_text("v1\n")
    (plain_vault / "Rot2Gold/Videos/video-old.md").write_text("old\n")
    (plain_vault / "Other.md").write_text("not ours\n")
    before = brain.snapshot()
    assert "Other.md" not in before
    (plain_vault / "Rot2Gold/Quotes.md").write_text("v2\n")
    (plain_vault / "Rot2Gold/Videos/video-new.md").write_text("new\n")
    (plain_vault / "Rot2Gold/Videos/video-old.md").unlink()
    (plain_vault / "Other.md").write_text("changed by the user\n")
    sha, paths = brain.finish(before, brain.note_paths(), "agent: test")
    assert sha is None
    assert paths == ["Rot2Gold/Quotes.md", "Rot2Gold/Videos/video-new.md", "Rot2Gold/Videos/video-old.md"]


def test_git_auto_uses_the_vault_repository_when_there_is_one(plain_vault):
    (plain_vault / ".git").mkdir()
    assert brain.uses_git()


def test_v8_makes_image_paths_relative_to_the_data_folder(tmp_path):
    path = tmp_path / "r2g.sqlite"
    con = db.connect(path)
    con.execute("INSERT INTO posts (id, url, status, added_at, updated_at) VALUES ('1', 'u', 'fetched', 'x', 'x')")
    con.execute("INSERT INTO images (post_id, idx, kind, path) VALUES ('1', 0, 'frame', 'data/media/1/frame.png')")
    con.execute("PRAGMA user_version = 7")
    con.commit()
    con.close()
    con = db.connect(path)
    assert con.execute("SELECT path FROM images").fetchone()[0] == "media/1/frame.png"
    assert (tmp_path / "r2g.sqlite.bak-v7").exists()
    assert sqlite3.connect(tmp_path / "r2g.sqlite.bak-v7").execute("SELECT path FROM images").fetchone()[0] \
        == "data/media/1/frame.png"


def test_prepare_creates_folders_templates_and_starters_but_never_overwrites(plain_vault):
    from rot2gold import vault
    made = vault.prepare()
    assert "Rot2Gold/Videos/" in made and "Rot2Gold/Templates/video-note.md" in made
    assert "## Posts by theme" in (plain_vault / "Rot2Gold/Rot2Gold.md").read_text()
    (plain_vault / "Rot2Gold/Quotes.md").write_text("mine\n")
    (plain_vault / "Rot2Gold/Templates/idea-note.md").write_text("my template\n")
    assert vault.prepare() == []
    assert (plain_vault / "Rot2Gold/Quotes.md").read_text() == "mine\n"
    assert (plain_vault / "Rot2Gold/Templates/idea-note.md").read_text() == "my template\n"


def test_prepare_refuses_a_missing_vault(tmp_path, monkeypatch):
    from rot2gold import vault
    path = tmp_path / "config.toml"
    path.write_text(tomli_w.dumps({"vault": {"path": str(tmp_path / "gone")}}))
    monkeypatch.setenv("R2G_CONFIG", str(path))
    with pytest.raises(config.ConfigError, match="does not exist"):
        vault.prepare()


@pytest.mark.parametrize("name", ["write-notes.md", "ideas.md"])
def test_prompts_name_only_the_users_own_paths(plain_vault, name):
    import re
    from rot2gold import notes
    cfg = config.load()
    cfg["vault"]["rules"] = "My rules.md"
    config.write_user({"vault": cfg["vault"], "notes": {"language": "Italian"}})
    text = notes.render(name, ids="1", count=1, today="2026-10-21", notes="", mode="", existing="", existing_count=0,
                        existing_learnings="", existing_learnings_count=0, existing_events="", existing_events_count=0,
                        ideas_dir="x", learnings_dir="x", events_dir="x", max_new=5, max_new_learnings=8, max_new_events=8)
    left = set(re.findall(r"{{\w+}}", text))
    assert not left, left
    assert str(plain_vault / "Rot2Gold/Rot2Gold.md") in text and "Italian" in text
    assert str(plain_vault / "My rules.md") in text
    assert not re.search(r"Marco|~/Projects|brain-index|commonplace", text)


def test_v9_keeps_firefox_and_cookies_come_from_the_chosen_browser(tmp_path):
    from rot2gold import connections
    from rot2gold.sources import Access
    path = tmp_path / "r2g.sqlite"
    con = db.connect(path)
    con.execute("INSERT INTO connections (platform, name, url, cookies_mode, firefox_profile, created_at, updated_at)"
                " VALUES ('tiktok', 'Old', 'https://www.tiktok.com/@x/collection/Old-1', 'always', '/p', 'x', 'x')")
    con.execute("ALTER TABLE connections DROP COLUMN cookie_browser")
    con.execute("PRAGMA user_version = 8")
    con.commit()
    con.close()
    con = db.connect(path)
    row = con.execute("SELECT cookie_browser, firefox_profile FROM connections").fetchone()
    assert tuple(row) == ("firefox", "/p")
    connections.update(con, 1, browser="chrome", profile="")
    assert con.execute("SELECT cookie_browser FROM connections").fetchone()[0] == "chrome"
    with pytest.raises(ValueError, match="browser must be one of"):
        connections.update(con, 1, browser="netscape")
    assert Access(cookies=True, browser="firefox", profile="/p").cookie_spec() == "firefox:/p"
    assert Access(cookies=True, browser="chrome").cookie_spec() == "chrome"


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    """An app nobody has set up yet, with nothing read from this computer."""
    from rot2gold import firstrun
    from rot2gold.web import app as web
    monkeypatch.setenv("R2G_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.setattr(firstrun, "checks", lambda cfg: [{"key": k, "name": k, "ok": k == "claude", "detail": "x"}
                                                         for k in ("claude", "codex", "gemini", "local", "tesseract", "ffmpeg")])
    monkeypatch.setattr(firstrun, "obsidian_vaults", lambda: [])
    monkeypatch.setattr(firstrun, "ocr_choices", lambda cfg: [])
    (tmp_path / "vault/.obsidian").mkdir(parents=True)
    return web, tmp_path


def _client(web):
    import httpx
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=web.app), base_url="http://127.0.0.1:8740",
                             headers={"Origin": "http://127.0.0.1:8740"})


FORM = {"vault_pick": "", "folder": "Rot2Gold", "provider": "claude", "backend": "subscription", "model": "",
        "local_url": "http://localhost:11434/v1", "language": "English", "browser": "firefox", "git": "1"}


def test_setup_first_run_redirects_saves_and_prepares_the_vault(fresh):
    import asyncio
    web, tmp = fresh

    async def run():
        async with _client(web) as client:
            first = await client.get("/ideas", follow_redirects=False)
            assert first.status_code == 303 and first.headers["location"] == "/setup"
            assert "Set up Rot2Gold" in (await client.get("/setup")).text
            bad = await client.post("/setup", data=FORM | {"vault_other": str(tmp / "missing"), "data_dir": str(tmp / "data"),
                                                           "key": "sk-do-not-echo"})
            assert "doesn&#39;t exist" in bad.text and "sk-do-not-echo" not in bad.text
            inside = await client.post("/setup", data=FORM | {"vault_other": str(tmp / "vault"), "data_dir": str(tmp / "vault/data")})
            assert "outside the vault" in inside.text
            done = await client.post("/setup", data=FORM | {
                "vault_other": str(tmp / "vault"), "data_dir": str(tmp / "data"),
                "collection": "https://www.tiktok.com/@example/collection/Saved-7000000000000000001"})
            assert "Ready" in done.text and "Added the collection Saved" in done.text
    asyncio.run(run())
    cfg = config.load()
    assert cfg["vault"]["path"] == str(tmp / "vault") and cfg["vault"]["videos"] == "Rot2Gold/Videos"
    assert cfg["storage"]["data_dir"] == str(tmp / "data") and cfg["vault"]["git"] == "auto"
    assert (tmp / "vault/Rot2Gold/Templates/video-note.md").is_file()
    con = db.connect(tmp / "data/r2g.sqlite")
    assert con.execute("SELECT name, cookie_browser FROM connections").fetchone()[:] == ("Saved", "firefox")


def test_setup_again_keeps_a_custom_layout(fresh):
    import asyncio
    web, tmp = fresh
    custom = {"path": str(tmp / "vault"), "videos": "Resources/commonplace/videos", "hub": "Resources/commonplace/commonplace.md",
              "ideas": "Inbox/ideas", "rules": "AGENTS.md"}
    (tmp / "config.toml").write_text(tomli_w.dumps({"vault": custom, "notes": {"model": "opus"}}))

    async def run():
        async with _client(web) as client:
            page = (await client.get("/setup")).text
            assert "custom layout" in page and 'name="folder" value=""' in page
            done = await client.post("/setup", data=FORM | {"folder": "", "vault_other": str(tmp / "vault"),
                                                            "data_dir": str(tmp / "data"), "model": "opus"})
            assert "Setup saved" in done.text
    asyncio.run(run())
    cfg = config.load()
    assert cfg["vault"]["videos"] == "Resources/commonplace/videos" and cfg["vault"]["rules"] == "AGENTS.md"
    assert cfg["notes"]["model"] == "opus"


def test_folder_browser_lists_only_visible_folders(fresh):
    import asyncio
    web, tmp = fresh
    (tmp / "vault/Notes").mkdir()
    (tmp / "vault/note.md").write_text("x")

    async def run():
        async with _client(web) as client:
            return (await client.get("/setup/dirs", params={"path": str(tmp / "vault")})).json()
    listing = asyncio.run(run())
    assert listing["vault"] is True and listing["dirs"] == [{"name": "Notes", "path": str(tmp / "vault/Notes")}]


def test_moving_the_data_folder_copies_then_removes(tmp_path):
    from rot2gold import firstrun
    old, new = tmp_path / "old", tmp_path / "new"
    con = db.connect(old / "r2g.sqlite")
    con.execute("INSERT INTO posts (id, url, status, added_at, updated_at) VALUES ('1', 'u', 'done', 'x', 'x')")
    con.commit()
    con.close()
    (old / "media/1").mkdir(parents=True)
    (old / "media/1/frame.png").write_bytes(b"png")
    firstrun.move_data(old, new)
    assert (new / "media/1/frame.png").read_bytes() == b"png" and not (old / "media").exists()
    assert db.connect(new / "r2g.sqlite").execute("SELECT id FROM posts").fetchone()[0] == "1"
    assert not (old / "r2g.sqlite").exists()
