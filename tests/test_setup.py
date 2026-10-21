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
