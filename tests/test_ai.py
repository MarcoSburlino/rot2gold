"""The AI providers: shared helpers, Codex and Gemini event parsing, and direct mode for local models."""

import json

import pytest
import tomli_w

from rot2gold import ai, config, db, direct, notes
from rot2gold.ai import base, codex_cli, gemini_cli, local


def test_strict_schema_closes_objects_and_requires_every_property():
    out = base.strict(notes.REPORT_SCHEMA)
    assert out["additionalProperties"] is False and set(out["required"]) == set(out["properties"])
    item = out["properties"]["posts"]["items"]
    assert item["required"] == ["id", "note_path", "skip_reason"] and item["additionalProperties"] is False
    assert notes.REPORT_SCHEMA["properties"]["posts"]["items"]["required"] == ["id"]  # the original is untouched


@pytest.mark.parametrize("text", ['{"a": 1}', 'Done.\n```json\n{"a": 1}\n```', 'All written. {"a": 1}'])
def test_json_from_text_finds_the_report(text):
    assert base.json_from_text(text) == {"a": 1}


def test_codex_events_become_a_result_and_log_lines():
    events = [
        {"type": "thread.started", "thread_id": "x"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "I'll start."}},
        {"type": "item.completed", "item": {"type": "command_execution", "command": "/bin/bash -lc 'r2g done 1 V/video-a.md'",
                                            "exit_code": 0}},
        {"type": "item.completed", "item": {"type": "command_execution", "command": "/bin/bash -lc 'cat x'"}},
        {"type": "item.completed", "item": {"type": "file_change", "changes": [{"path": "/v/V/video-a.md", "kind": "add"}]}},
        {"type": "item.completed", "item": {"type": "web_search", "query": "spacing effect"}},
        {"type": "item.completed", "item": {"type": "agent_message", "text": '{"posts": [], "new_tags": []}'}},
        {"type": "turn.completed", "usage": {"input_tokens": 100, "cached_input_tokens": 60, "output_tokens": 9}},
    ]
    res, lines = base.Result(), []
    for ev in events:
        codex_cli.parse_event(ev, res, lines.append)
    assert res.ok and res.structured == {"posts": [], "new_tags": []}
    assert lines == ["r2g done 1 V/video-a.md", "write video-a.md", "search: spacing effect"]
    assert res.usage["cache_read"] == 60 and res.turns == 4
    failed = base.Result()
    codex_cli.parse_event({"type": "turn.failed", "error": {"message": "You've hit your usage limit."}}, failed, lines.append)
    assert not failed.ok and failed.limited


def test_codex_command_uses_the_sandbox_schema_and_stdin(monkeypatch, tmp_path):
    seen = {}

    class Proc:
        def __init__(self, cmd, **kw):
            seen["cmd"], seen["env"] = cmd, kw["env"]
            seen["schema"] = json.loads(open(cmd[cmd.index("--output-schema") + 1]).read())
            self.stdin = type("In", (), {"write": lambda s, v: seen.update(prompt=v), "close": lambda s: None})()
            self.stdout = iter([json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": '{"ok": true}'}}),
                                json.dumps({"type": "turn.completed", "usage": {}})])
            self.returncode = 0

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(codex_cli.shutil, "which", lambda name: "/fake/codex")
    monkeypatch.setattr(codex_cli.subprocess, "Popen", Proc)
    res = codex_cli.run("the prompt", schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
                        cwd=str(tmp_path), add_dirs=["/data"], model="", api_key="secret")
    cmd = seen["cmd"]
    assert res.ok and seen["prompt"] == "the prompt" and cmd[-1] == "-"
    assert cmd[cmd.index("--sandbox") + 1] == "workspace-write" and "-m" not in cmd
    assert cmd[cmd.index("--add-dir") + 1] == "/data" and seen["env"]["CODEX_API_KEY"] == "secret"
    assert seen["schema"]["additionalProperties"] is False and "secret" not in " ".join(cmd)


def test_gemini_events_keep_the_text_after_the_last_tool_call():
    res, lines, answer = base.Result(), [], []
    for ev in [{"type": "message", "role": "assistant", "content": "Let me read it.", "delta": True},
               {"type": "tool_use", "tool_name": "write_file", "parameters": {"file_path": "/v/video-b.md"}},
               {"type": "tool_use", "tool_name": "run_shell_command", "parameters": {"command": "r2g done 2 V/video-b.md"}},
               {"type": "message", "role": "assistant", "content": '{"posts": [', "delta": True},
               {"type": "message", "role": "assistant", "content": "]}", "delta": True},
               {"type": "result", "status": "success", "stats": {"input_tokens": 50, "output_tokens": 5, "cached": 10,
                                                                 "duration_ms": 900}}]:
        gemini_cli.parse_event(ev, res, lines.append, answer)
    assert res.ok and res.structured == {"posts": []} and res.duration_ms == 900
    assert lines == ["write video-b.md", "r2g done 2 V/video-b.md"]
    quota = base.Result()
    gemini_cli.parse_event({"type": "result", "status": "error", "error": {"message": "Quota exceeded (429)"}},
                           quota, lines.append, [])
    assert quota.limited


def test_gemini_policy_allows_only_file_web_and_r2g_tools():
    policy = __import__("tomllib").loads(gemini_cli.POLICY)
    shell = next(r for r in policy["rule"] if r["toolName"] == "run_shell_command")
    assert all(p.startswith(("r2g ", "rg ")) for p in shell["commandPrefix"])
    assert all(r["decision"] == "allow" for r in policy["rule"])


def test_run_agent_dispatches_by_provider(monkeypatch):
    calls = []
    monkeypatch.setattr(codex_cli, "run", lambda prompt, **kw: calls.append(("codex", kw["model"])) or base.Result(ok=True))
    cfg = {"ai": {"provider": "codex"}, "notes": {"backend": "subscription"}}
    ai.run_agent(cfg, "p", schema={}, cwd=".", add_dirs=[], model="gpt-x", on_line=print)
    assert calls == [("codex", "gpt-x")]
    assert ai.run_label(cfg) == "codex" and ai.run_label({"ai": {}, "notes": {"backend": "api"}}) == "api"


def test_local_chat_sends_a_strict_schema(monkeypatch):
    sent = {}

    class Response:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": '{"ok": true}'}}], "usage": {"prompt_tokens": 7, "completion_tokens": 2}}

    def post(url, json=None, headers=None, timeout=None):
        sent.update(url=url, body=json, headers=headers)
        return Response()

    monkeypatch.setattr(local.httpx, "post", post)
    res = local.chat("hi", schema={"type": "object", "properties": {"ok": {"type": "boolean"}}}, model="qwen3:8b",
                     url="http://localhost:11434/v1/", api_key="k")
    assert res.ok and res.structured == {"ok": True} and res.usage["tokens_in"] == 7
    assert sent["url"] == "http://localhost:11434/v1/chat/completions" and sent["headers"]["Authorization"] == "Bearer k"
    assert sent["body"]["response_format"]["json_schema"]["schema"]["required"] == ["ok"]


@pytest.fixture
def local_vault(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "Rot2Gold/Videos").mkdir(parents=True)
    path = tmp_path / "config.toml"
    path.write_text(tomli_w.dumps({"vault": {"path": str(vault)}, "ai": {"provider": "local"},
                                   "notes": {"model": "qwen3:8b"}, "ideas": {"model": "qwen3:8b"}}))
    monkeypatch.setenv("R2G_CONFIG", str(path))
    monkeypatch.setattr(direct.notefile, "brain_dir", lambda cfg=None: vault)
    from rot2gold import vault as vault_module
    vault_module.prepare()
    con = db.connect(tmp_path / "r2g.sqlite")
    for pid, creator in (("1", "ana"), ("2", "ben")):
        con.execute("INSERT INTO posts (id, url, creator, upload_date, type, status, added_at, updated_at)"
                    " VALUES (?, ?, ?, '2026-10-01', 'video', 'processed', 'x', 'x')", (pid, f"https://example.com/{pid}", creator))
    con.commit()
    return vault, con


ANSWER = {"skip_reason": None, "title": "Spacing reviews beats cramming", "description": "Why spaced review works",
          "content_language": "en", "topic_tags": ["Memory", "learning"], "key_points": ["The creator argues for spacing."],
          "content": "### On-screen text (0.5 s)\n\nStop cramming\n\n### Transcript\n\nReview it tomorrow.",
          "mentioned": ["Hermann Ebbinghaus"], "context": "The spacing effect is well studied.", "further_reading": [],
          "insights": ["An example of the spacing effect."], "theme": "Learning and memory",
          "hub_line": "spacing beats cramming", "quotes": ["Review it tomorrow."]}


def test_direct_mode_writes_the_note_hub_quotes_and_marks_done(local_vault, monkeypatch):
    vault, con = local_vault
    answers = [ANSWER, ANSWER | {"skip_reason": "music only"}]
    monkeypatch.setattr(local, "chat", lambda prompt, **kw: base.Result(ok=True, structured=answers.pop(0), turns=1))
    res = direct.write_notes(con, ["1", "2"], config.load())
    assert res.ok and [p["note_path"] for p in res.structured["posts"]] == ["Rot2Gold/Videos/video-spacing-reviews-beats-cramming.md", None]
    note = (vault / "Rot2Gold/Videos/video-spacing-reviews-beats-cramming.md").read_text()
    assert 'post_id: "1"' in note and "  - memory" in note and "Not checked" in note and note.rstrip().endswith("## My notes")
    hub = (vault / "Rot2Gold/Rot2Gold.md").read_text()
    assert "### Learning and memory\n\n- [[video-spacing-reviews-beats-cramming]] — spacing beats cramming" in hub
    assert "- learning\n- memory" in hub and res.structured["new_tags"] == ["memory", "learning"]
    assert '"Review it tomorrow." — @ana, [[video-spacing-reviews-beats-cramming]]' in (vault / "Rot2Gold/Quotes.md").read_text()
    statuses = dict(con.execute("SELECT id, status FROM posts"))
    assert statuses == {"1": "done", "2": "skipped"}
    assert notes.check_batch(con, ["1", "2"], lambda *a, **k: None) == (1, 1)


def test_direct_ideas_create_then_update_with_a_new_source(local_vault, monkeypatch):
    vault, con = local_vault
    from rot2gold import ideas
    for pid, name in (("1", "video-a"), ("2", "video-b")):
        (vault / f"Rot2Gold/Videos/{name}.md").write_text(f'---\ncreator: "@{pid}"\n---\n# {name}\n\n## Key points\n\n- spaced review\n')
        con.execute("UPDATE posts SET status = 'done', note_path = ? WHERE id = ?", (f"Rot2Gold/Videos/{name}.md", pid))
    con.commit()
    item = {"kind": "idea", "action": "create", "file": "", "title": "Try spaced review", "description": "Review at growing gaps",
            "summary": "Two posts recommend it.", "when": "", "until": "", "where": "", "topic_tags": ["learning"],
            "sources": [{"note": "video-a", "line": "says review tomorrow"}, {"note": "video-ghost", "line": "x"}]}
    replies = [{"items": [item], "considered": ["1"], "notes": ["1 → new idea"]},
               {"items": [item | {"action": "update", "file": "idea-try-spaced-review.md",
                                  "sources": [{"note": "video-b", "line": "also says so"}]}],
                "considered": ["2"], "notes": []}]
    monkeypatch.setattr(local, "chat", lambda prompt, **kw: base.Result(ok=True, structured=replies.pop(0)))
    needs = {"1": {"idea": True}, "2": {"idea": True}}
    known = {k: ideas.list_items(k) for k in ideas.KINDS}
    res = direct.find_ideas(con, ["1"], needs, known, config.load(), None)
    path = vault / "Rot2Gold/Ideas/idea-try-spaced-review.md"
    assert res.structured["created"] == [str(path)] and res.structured["considered"] == ["1"]
    text = path.read_text()
    assert "support: 1" in text and "[[video-ghost]]" not in text and "status: new" in text
    path.write_text(text.replace("## My notes\n", "## My notes\n\nMine, keep it.\n"))
    known = {k: ideas.list_items(k) for k in ideas.KINDS}
    res = direct.find_ideas(con, ["2"], needs, known, config.load(), None)
    text = path.read_text()
    assert res.structured["updated"] == [str(path)] and "support: 2" in text
    assert "- [[video-b]] — also says so" in text and "new support: [[video-b]]" in text and "Mine, keep it." in text


def test_direct_learning_gets_a_try_it_section_that_grows():
    """Gold: a learning carries what its sources suggest doing; an update adds only new actions, before the Log."""
    item = {"title": "Spacing beats cramming", "description": "d", "summary": "s", "topic_tags": [],
            "try_it": ["Review tomorrow ([[video-a]])", "- Review tomorrow ([[video-a]])", " "]}
    text = direct.new_item(item, "learning", [{"note": "video-a", "line": "says so"}], {}, "2026-10-27")
    assert "## Try it\n\n- Review tomorrow ([[video-a]])\n\n## Log" in text  # blank and repeated lines dropped
    assert "## Try it" not in direct.new_item(item | {"try_it": []}, "learning", [{"note": "video-a", "line": "x"}], {}, "2026-10-27")
    assert "## Try it" not in direct.new_item(item, "idea", [{"note": "video-a", "line": "x"}], {}, "2026-10-27")
    bare = direct.new_item(item | {"try_it": []}, "learning", [{"note": "video-a", "line": "x"}], {}, "2026-10-27")
    more = {"try_it": ["Review tomorrow ([[video-a]])", "Use flashcards ([[video-b]])"]}
    updated = direct.update_item(bare, "learning", [{"note": "video-b", "line": "y"}], {}, "2026-10-28", more)
    assert updated.index("## Try it") < updated.index("## Log")
    assert "- Review tomorrow ([[video-a]])\n- Use flashcards ([[video-b]])" in updated
    again = direct.update_item(updated, "learning", [{"note": "video-c", "line": "z"}], {}, "2026-10-29", more)
    assert again.count("Use flashcards") == 1  # an action already there is not added twice


def test_direct_mode_ignores_a_skip_for_a_post_with_speech(local_vault, monkeypatch):
    vault, con = local_vault
    con.execute("INSERT INTO segments (post_id, idx, start, end, text) VALUES ('1', 0, 0, 5, ?)",
                (" ".join(["word"] * 20),))
    con.commit()
    monkeypatch.setattr(local, "chat", lambda prompt, **kw: base.Result(ok=True, structured=ANSWER | {"skip_reason": "no speech"}))
    res = direct.write_notes(con, ["1"], config.load())
    assert res.structured["posts"][0]["note_path"] and con.execute("SELECT status FROM posts WHERE id = '1'").fetchone()[0] == "done"


def test_tidy_drops_timestamps_and_spaces_headings():
    assert direct.tidy("### Transcript\n[0:00.0–0:08.0] Hello.\n[1:02–1:09] Bye.") == "### Transcript\n\nHello.\nBye."
