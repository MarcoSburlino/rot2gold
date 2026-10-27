"""Ideas selection, parsing, migrations and batch side effects in temporary folders."""

import sqlite3
import subprocess

import pytest

from rot2gold import brain, db, extract, ideas, lock, notefile, undo
from rot2gold.ai import claude_cli


@pytest.fixture
def vault(tmp_path, monkeypatch):
    root = tmp_path / "brain"
    (root / "Resources/commonplace").mkdir(parents=True)
    (root / "Inbox/ideas").mkdir(parents=True)
    for module in (brain, ideas, notefile):
        monkeypatch.setattr(module, "brain_dir", lambda cfg=None: root)
    monkeypatch.setattr(ideas, "DATA", tmp_path / "data")
    return root


@pytest.fixture
def con(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "load", lambda: {})
    monkeypatch.setattr(db, "LINKS", tmp_path / "no-links")
    return db.connect(tmp_path / "r2g.sqlite")


def post(con, pid, day, theme="video-one"):
    con.execute("INSERT INTO posts (id, url, status, note_path, added_at, updated_at)"
                " VALUES (?, ?, 'done', ?, ?, ?)",
                (pid, "url", f"Resources/commonplace/videos/{theme}.md", day, day))
    con.commit()


def test_themes_and_candidates(vault, con):
    (vault / "Resources/commonplace/commonplace.md").write_text(
        "# Hub\n## Other\n- [[ignored]]\n## Posts by theme\n### Learning and memory\n"
        "- [[video-one]] — a\n### Money and business\n- [[video-two]] — b\n## Next\n- [[video-three]]\n")
    assert ideas.themes() == {"Learning and memory": ["video-one"], "Money and business": ["video-two"]}
    post(con, "1", "2026-10-18T12:00:00", "video-one")
    post(con, "2", "2026-10-19T12:00:00", "video-two")
    post(con, "3", "2026-10-20T12:00:00", "video-one")
    con.execute("UPDATE posts SET ideas_checked_at = 'x' WHERE id = '3'")
    con.execute("INSERT INTO connections (id, platform, name, url, created_at, updated_at)"
                " VALUES (1, 'tiktok', 'c', 'u', 'x', 'x')")
    con.execute("INSERT INTO connection_posts VALUES (1, '2', 'x')")
    con.commit()
    cfg = {"ideas": {"since": "2026-10-19"}}
    # Learnings and events have no date limit: every note not checked for them is a candidate, new ones for ideas first.
    assert ideas.candidates_new(con, cfg=cfg) == ["2", "1", "3"]
    con.execute("UPDATE posts SET learnings_checked_at = 'x', events_checked_at = 'x'")
    assert ideas.candidates_new(con, cfg=cfg) == ["2"]
    assert ideas.candidates_new(con, [1], cfg) == ["2"]
    assert ideas.candidates_new(con, [99], cfg) == []
    assert ideas.candidates_rebuild(con, None) == ["1", "2"]
    assert ideas.candidates_rebuild(con, ["Learning and memory"]) == ["1"]
    con.execute("UPDATE posts SET learnings_checked_at = NULL WHERE id = '3'")  # checked for ideas, not learnings
    assert ideas.candidates_new(con, cfg=cfg) == ["2", "3"]
    assert ideas.candidates_rebuild(con, None) == ["1", "2", "3"]
    assert ideas._checks(con, ["2", "3"]) == {"2": {"idea": True, "learning": False, "event": False},
                                              "3": {"idea": False, "learning": True, "event": False}}
    con.execute("UPDATE posts SET learnings_checked_at = 'x', events_checked_at = NULL WHERE id = '3'")  # only events left
    assert ideas.candidates_new(con, cfg=cfg) == ["2", "3"]
    assert ideas.look_for(ideas._checks(con, ["3"])["3"]) == "events"
    assert ideas.look_for(ideas._checks(con, ["2"])["2"]) == "ideas"
    with pytest.raises(ValueError, match="Known themes:.*Learning and memory"):
        ideas.candidates_rebuild(con, ["Unknown"])


def test_list_ideas_and_tolerant_front_matter(vault):
    (vault / "Inbox/ideas/idea-one.md").write_text(
        "---\ndescription: The line credited to X: confidence comes from proof\n"
        "sources:\n  - [[video-one]]\n  - \"[[other]]\"\ntags:\n  - idea\n---\n# Try proof\n")
    (vault / "Inbox/ideas/idea-two.md").write_text(
        "---\nsupport: 3\nupdated: 2026-10-20\nsources:\n  - \"[[video-two]]\"\n---\n# Try another\n")
    rows = ideas.list_ideas()
    assert [r["name"] for r in rows] == ["idea-one", "idea-two"]  # support is counted, not read: 2 sources vs 1
    assert rows[0]["description"] == "The line credited to X: confidence comes from proof"
    assert rows[0]["sources"] == ["video-one", "other"]
    assert rows[0]["support"] == 2 and rows[0]["status"] == "new"
    assert rows[1]["sources"] == ["video-two"] and rows[1]["support"] == 1
    assert notefile.read(vault / "Inbox/ideas/idea-one.md").meta["tags"] == ["idea"]


def test_support_counts_creators_and_recount_fixes_the_file(vault):
    """Videos by the same creator count once; recount writes that number into the item's front matter."""
    videos = vault / "Resources/commonplace/videos"
    videos.mkdir()
    for name, creator in (("video-a", "ann"), ("video-b", "ann"), ("video-c", "bob")):
        (videos / f"{name}.md").write_text(f"---\ncreator: {creator}\n---\n# {name}\n")
    path = vault / "Inbox/ideas/idea-one.md"
    path.write_text('---\ndescription: One\nsupport: 7\nsources:\n  - "[[video-a]]"\n  - "[[video-b]]"\n'
                    '  - "[[video-c]]"\n  - "[[other-note]]"\n---\n# Try it\n\nsupport: in the body stays\n')
    names = notefile.brain_names()
    assert notefile.support(["video-a", "video-b", "video-c", "other-note"], names) == 3  # ann, bob, the note
    assert ideas.list_ideas()[0]["support"] == 3
    assert ideas.recount(path, names) is True
    text = path.read_text()
    assert "support: 3\n" in text and "support: 7" not in text and "support: in the body stays" in text
    assert ideas.recount(path, names) is False  # already right: the file is left alone
    path.write_text('---\ndescription: One\nsources:\n  - "[[video-c]]"\n---\n# Try it\n')
    assert ideas.recount(path, names) is True
    assert path.read_text().startswith('---\ndescription: One\nsupport: 1\nsources:')


def test_gold_merge_folds_linked_ideas_into_their_learnings(vault):
    """Gold: an idea linked to a learning becomes a line in its Try it, bringing its sources and the
    user's notes; links follow it; pure-action and dropped ideas stay."""
    from rot2gold import gold
    (vault / "Inbox/learnings").mkdir()
    (vault / "Inbox/events").mkdir()
    learning = vault / "Inbox/learnings/learning-proof.md"
    learning.write_text(
        '---\ndescription: "Proof builds confidence"\ncreated: 2026-10-20\nupdated: 2026-10-20\nsupport: 1\n'
        'sources:\n  - "[[video-a]]"\nstatus: new\ntags:\n  - learning\n---\n\n# Confidence grows from proof\n\n'
        '> [!note] AI-generated learning.\n\nThe paragraph.\n\n## What each source adds\n\n- [[video-a]] — the line\n\n'
        '## Use it\n\n- [[idea-stack]]\n- [[idea-other]]\n\n## Log\n\n- 2026-10-20 — created from [[video-a]]\n\n## My notes\n\n')
    (vault / "Inbox/ideas/idea-stack.md").write_text(
        '---\ndescription: "Stack proof"\nsupport: 2\nsources:\n  - "[[video-a]]"\n  - "[[video-b]]"\nstatus: trying\n---\n\n'
        '# Build a stack of proof\n\n> [!note] AI-generated idea.\n\nDo the thing you doubt,\nagain and again.\n\n'
        '## Why sources point here\n\n- [[video-a]] — first\n- [[video-b]] — second, new to the learning\n\n'
        '## Learnings behind it\n\n- [[learning-proof]]\n\n## My notes\n\nI tried this in March.\n')
    (vault / "Inbox/ideas/idea-other.md").write_text(
        '---\nstatus: dropped\nsources:\n  - "[[video-a]]"\n---\n# A dropped idea\n\nText.\n\n## Learnings behind it\n\n- [[learning-proof]]\n')
    (vault / "Inbox/ideas/idea-book.md").write_text('---\nstatus: new\nsources:\n  - "[[video-c]]"\n---\n# Read a book\n\nText.\n')
    (vault / "Inbox/events/event-talk.md").write_text('---\nwhen: 2026\nsources:\n  - "[[video-a]]"\n---\n# A talk\n\nSee [[idea-stack|the idea]].\n')

    found = gold.plan()
    assert [(p["idea"]["name"], p["learning"]["name"], p["new_sources"]) for p in found["pairs"]] == [
        ("idea-stack", "learning-proof", ["video-b"])]
    assert [i["name"] for i in found["alone"]] == ["idea-book"] and [i["name"] for i in found["dropped"]] == ["idea-other"]

    lines = []
    gold.merge(lambda line, **kw: lines.append(line), today="2026-10-27")
    text = learning.read_text()
    assert not (vault / "Inbox/ideas/idea-stack.md").exists() and (vault / "Inbox/ideas/idea-book.md").exists()
    assert '  - "[[video-a]]"\n  - "[[video-b]]"\nstatus: trying' in text  # its source, and the status the user set
    assert "updated: 2026-10-27" in text and "support: 2" in text
    assert "- [[video-a]] — the line\n- [[video-b]] — second, new to the learning\n" in text
    assert "## Use it" not in text and "[[idea-stack]]" not in text
    assert "## Try it\n\n- [[idea-other]]\n- **Build a stack of proof.** Do the thing you doubt, again and again.\n" in text
    assert "## Log\n\n- 2026-10-27 — merged in the idea “Build a stack of proof”: its action is under Try it, with 1 more source\n" in text
    assert "From the idea “Build a stack of proof”:\n\nI tried this in March." in text
    assert ideas.list_items("learning")[0]["try_it"] is True
    assert "See [[learning-proof|the idea]]." in (vault / "Inbox/events/event-talk.md").read_text()
    assert lines == ["merged idea idea-stack into learning-proof; links updated in event-talk.md"]
    assert gold.plan()["pairs"] == []  # running it again changes nothing


def test_v2_to_v3_without_backup(tmp_path, monkeypatch):
    path = tmp_path / "r2g.sqlite"
    old = sqlite3.connect(path)
    old.executescript(db.SCHEMA + db.SCHEMA_V2)
    old.execute("PRAGMA user_version = 2")
    old.commit()
    old.close()
    monkeypatch.setattr(db, "load", lambda: {})
    monkeypatch.setattr(db, "LINKS", tmp_path / "no-links")
    con = db.connect(path)
    assert con.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    assert {"kind", "ideas_created", "ideas_updated"} <= db.columns(con, "runs")
    assert not (tmp_path / "r2g.sqlite.bak-v1").exists()
    db.connect(path)


@pytest.mark.parametrize("dry_run", [False, True])
def test_run_pass(vault, con, monkeypatch, dry_run):
    def git(*args):
        return subprocess.run(["git", "-C", str(vault), *args], check=True, capture_output=True, text=True).stdout
    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    note = vault / "Resources/commonplace/video-one.md"
    note.write_text("# Source\n")
    other = vault / "Projects/other.md"
    other.parent.mkdir()
    other.write_text("old\n")
    git("add", "--", "Resources/commonplace/video-one.md", "Projects/other.md")
    git("commit", "-q", "-m", "init")
    post(con, "1", "2026-10-19T12:00:00", "video-one")
    con.execute("INSERT INTO runs (origin, started_at) VALUES ('terminal', 'x')")
    con.commit()
    monkeypatch.setattr(brain, "run_after_write", lambda cfg=None: None)
    folder = ideas.DATA / "ideas-dry-run/run-1" if dry_run else vault / "Inbox/ideas"

    learnings = ideas.DATA / "ideas-dry-run/run-1" if dry_run else vault / "Inbox/learnings"
    events = ideas.DATA / "ideas-dry-run/run-1" if dry_run else vault / "Inbox/events"
    (vault / "Inbox/learnings").mkdir(exist_ok=True)
    (vault / "Inbox/learnings/learning-old.md").write_text(
        "---\ndescription: Old one\nstatus: kept\nsources:\n  - \"[[video-zero]]\"\n---\n# Old learning\n")
    (vault / "Inbox/events").mkdir(exist_ok=True)
    (vault / "Inbox/events/event-old.md").write_text(
        "---\ndescription: An old event\nwhen: 1983-06\nsources:\n  - \"[[video-zero]]\"\n---\n# Old event\n")

    def fake(prompt, **kwargs):
        assert "1  Resources/commonplace/videos/video-one.md  [ideas, learnings and events]" in prompt
        assert str(folder) in prompt and str(learnings) in prompt and str(events) in prompt
        assert "learning-old.md · Old learning · Old one · kept · video-zero" in prompt  # existing learnings listed
        assert "event-old.md · Old event · 1983-06 · An old event · new · video-zero" in prompt  # events with their date
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "idea-proof.md").write_text(
            "---\ndescription: Try proof\nsupport: 1\nsources:\n  - \"[[video-one]]\"\n---\n# Try proof\n")
        (learnings / "learning-proof-helps.md").write_text(
            "---\ndescription: Proof helps\nsupport: 1\nsources:\n  - \"[[video-one]]\"\n---\n# Proof helps\n")
        (events / "event-proof-day.md").write_text(
            "---\ndescription: Proof day\nwhen: 2026-11-12\nsupport: 1\nsources:\n  - \"[[video-one]]\"\n---\n# Proof day\n")
        other.write_text("unrelated change\n")
        return claude_cli.Result(ok=True, structured={"created": [str(folder / "idea-proof.md"), "learning-proof-helps.md",
                                                                  "Inbox/events/event-proof-day.md"],
                                                      "updated": [], "considered": ["1"], "notes": ["done"]})
    monkeypatch.setattr(claude_cli, "run", fake)
    cfg = {"vault": {"path": str(vault)}, "ideas": {"batch_size": 25, "model": "opus", "max_new_per_pass": 5},
           "notes": {"backend": "subscription", "stop_at_plan_usage": 0.9}}
    messages = []
    found = ideas.run_pass(con, ["1"], cfg, lambda msg, **kw: messages.append(msg), 1, dry_run)
    assert len(found["created"]) == 1 and len(found["learnings_created"]) == 1 and found["considered"] == ["1"]
    assert len(found["events_created"]) == 1  # a path relative to the brain is accepted too
    batch = con.execute("SELECT * FROM batches WHERE run_id = 1").fetchone()
    assert batch["kind"] == "ideas" and batch["post_ids"] == "1"
    assert batch["considered"] == batch["learned"] == batch["events_seen"] == ("" if dry_run else "1")
    run = con.execute("SELECT ideas_created, learnings_created, events_created FROM runs WHERE id = 1").fetchone()
    assert tuple(run) == (1, 1, 1)
    columns = "ideas_checked_at, learnings_checked_at, events_checked_at"
    checked = tuple(con.execute(f"SELECT {columns} FROM posts WHERE id = '1'").fetchone())
    if dry_run:
        assert checked == (None, None, None)
        assert git("log", "-1", "--format=%s").strip() == "init"
        manifest = ideas.read_manifest(folder)
        assert manifest["considered"] == manifest["learned"] == manifest["events_seen"] == ["1"]
        assert "learning-old.md" in manifest["base"] and "event-old.md" in manifest["base"]
    else:
        assert all(checked)
        assert git("show", "--format=", "--name-only", "HEAD").split() == [
            "Inbox/events/event-proof-day.md", "Inbox/ideas/idea-proof.md",
            "Inbox/learnings/learning-proof-helps.md"]  # the old ones were already uncommitted
        con.execute("UPDATE runs SET status = 'ok' WHERE id = 1")
        undo.undo_run(con, 1, lambda *a, **k: None)  # every check comes back, so the notes are read again
        checked = tuple(con.execute(f"SELECT {columns} FROM posts WHERE id = '1'").fetchone())
        assert checked == (None, None, None)
        assert not (learnings / "learning-proof-helps.md").exists() and not (events / "event-proof-day.md").exists()
    assert "Projects/other.md" in git("status", "--porcelain")


def test_extract_records_ideas_stage(tmp_path, con, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "r2g.sqlite")
    monkeypatch.setattr(lock, "DATA", tmp_path)
    monkeypatch.setattr(lock, "LOCK_PATH", tmp_path / "r2g.lock")
    monkeypatch.setattr(extract, "load", lambda: {
        "notes": {"backend": "subscription", "model": "opus", "max_per_run": 20},
        "ideas": {"model": "opus"}, "vault": {"path": str(tmp_path)}})
    monkeypatch.setattr(extract.vault, "prepare", lambda cfg: ["Rot2Gold/Videos/"])
    monkeypatch.setattr(extract, "connections", lambda con, ids: [{"id": 1, "name": "Test"}])
    monkeypatch.setattr(extract, "sync_connection", lambda con, conn, report: (0, None))
    monkeypatch.setattr(extract, "fetch", lambda *a, **kw: 0)
    monkeypatch.setattr(extract, "process", lambda *a, **kw: 0)
    monkeypatch.setattr(ideas, "candidates_new", lambda *a, **kw: ["1"])
    monkeypatch.setattr(ideas, "run_pass", lambda *a, **kw: {"created": ["idea-a"], "updated": [], "considered": ["1"],
                                                              "learnings_created": ["l1", "l2"], "learnings_updated": []})
    row = extract.extract([1], quiet=True)
    assert row["kind"] == "extract" and row["ideas_created"] == 1 and row["status"] == "ok"
    assert row["learnings_created"] == 2
    assert [r[0] for r in con.execute("SELECT stage FROM run_events WHERE stage IS NOT NULL AND message LIKE '── %'")][-2:] == ["ideas", "done"]


def test_apply_dry_run_copies_new_and_never_overwrites_edits(vault, con, monkeypatch):
    """Applying a reviewed dry run costs no Claude call and must not clobber ideas the user edited since."""
    import json
    subprocess.run(["git", "init", "-q", str(vault)], check=True)
    subprocess.run(["git", "-C", str(vault), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
                    "--allow-empty", "-m", "init"], check=True)
    monkeypatch.setattr(brain, "run_after_write", lambda cfg=None: None)
    for pid in ("1", "2"):
        post(con, pid, "2026-10-15")
    kept = vault / "Inbox/ideas/idea-kept.md"
    kept.write_text("original\n")
    edited = vault / "Inbox/ideas/idea-edited.md"
    edited.write_text("original\n")
    folder = ideas.dry_run_dir(5)
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps({"considered": ["1", "2"], "base": {
        "idea-kept.md": ideas._sha(kept), "idea-edited.md": ideas._sha(edited)}}))
    for name in ("idea-kept.md", "idea-edited.md", "idea-new.md"):
        (folder / name).write_text("from the dry run\n")
    edited.write_text("The user changed status: trying\n")  # after the dry run

    done = ideas.apply_dry_run(con, 5, lambda *a, **k: None)
    assert sorted(done["copied"]) == ["idea-kept.md", "idea-new.md"] and done["skipped"] == ["idea-edited.md"]
    assert done["counts"] == {"ideas_created": 1, "ideas_updated": 1, "learnings_created": 0, "learnings_updated": 0,
                              "events_created": 0, "events_updated": 0}
    assert edited.read_text() == "The user changed status: trying\n"
    assert (vault / "Inbox/ideas/idea-new.md").read_text() == "from the dry run\n"
    assert con.execute("SELECT COUNT(*) FROM posts WHERE ideas_checked_at IS NOT NULL").fetchone()[0] == 2
    assert done["commit"]
    with pytest.raises(ValueError, match="already applied"):
        ideas.apply_dry_run(con, 5, lambda *a, **k: None)


def test_event_timing_and_date_order():
    """Coming up until the last day has passed; a month or year alone only until it begins."""
    from datetime import date
    today = date(2026, 10, 20)
    cases = {("2026-10-20", ""): "upcoming", ("2026-10-19", ""): "past", ("2026-10-01", "2026-10-25"): "upcoming",
             ("2026-11", ""): "upcoming", ("2026-10", ""): "past", ("2027", ""): "upcoming", ("2026", ""): "past",
             ("1983-06", ""): "past", ("", ""): "undated", ("soon", ""): "undated"}
    for (when, until), timing in cases.items():
        assert ideas.event_timing(when, until, today) == timing, (when, until)
    items = [{"name": n, "when": w, "until": "", "timing": ideas.event_timing(w, "", today)}
             for n, w in (("a", "1983"), ("b", "2026-12-01"), ("c", ""), ("d", "2026-11-02"), ("e", "2026-09-30"))]
    assert [i["name"] for i in ideas.sort_events(items)] == ["d", "b", "e", "a", "c"]
