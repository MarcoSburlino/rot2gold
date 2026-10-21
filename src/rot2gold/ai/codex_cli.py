"""Run OpenAI's Codex CLI non-interactively (`codex exec --json`) and read its event stream.

It works like Claude Code here: it reads the rules and the post data, writes notes in the vault, searches
the web and runs `r2g`. Its sandbox (workspace-write) lets commands write only in the vault and the
folders added with --add-dir, without network access; web search is Codex's own tool.
Login: the user's ChatGPT sign-in (`codex login`), or an OpenAI API key from the keychain.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import time

from ..errors import ToolMissing, UsageLimit
from .base import Result, interrupt, is_limit, json_from_text, strict


def describe_item(item: dict) -> str | None:
    """One short line for the run log, or None for items not worth showing."""
    kind = item.get("type")
    if kind == "command_execution":  # Codex wraps commands (/bin/bash -lc '…') and may chain or path them
        found = re.search(r"\br2g (done|skip|pending)\b[^'\"&;|]*", item.get("command", ""))
        return found.group(0).strip() if found else None
    if kind == "file_change":
        return ", ".join(f"{'write' if c.get('kind') == 'add' else 'edit'} {os.path.basename(c.get('path', ''))}"
                         for c in item.get("changes") or []) or None
    if kind == "web_search" and item.get("query"):
        return f"search: {item['query'][:80]}"
    return None


def parse_event(ev: dict, res: Result, on_line) -> None:
    t = ev.get("type")
    if t == "item.completed":
        item = ev.get("item") or {}
        if item.get("type") == "agent_message":
            res.text = item.get("text") or ""
        elif (line := describe_item(item)):
            on_line(line)
        if item.get("type") in ("command_execution", "file_change", "web_search", "mcp_tool_call"):
            res.turns += 1
    elif t == "turn.completed":
        u = ev.get("usage") or {}
        res.usage = {"tokens_in": u.get("input_tokens", 0), "tokens_out": u.get("output_tokens", 0),
                     "cache_read": u.get("cached_input_tokens", 0), "cache_write": u.get("cache_write_input_tokens", 0)}
        res.structured = json_from_text(res.text)
        res.ok = res.structured is not None
        if not res.ok:
            res.error = "Codex finished without the JSON report: " + res.text[:300]
    elif t in ("turn.failed", "error"):
        message = (ev.get("error") or {}).get("message") if t == "turn.failed" else ev.get("message")
        res.ok = False
        res.error = str(message or t)[:500]
        if is_limit(res.error):
            res.limited = True


def command(exe: str, schema_file: str, cwd: str, add_dirs: list[str], model: str) -> list[str]:
    cmd = [exe, "exec", "--json", "--skip-git-repo-check", "--ephemeral", "--sandbox", "workspace-write",
           "-C", cwd, "--output-schema", schema_file, "-c", 'web_search="live"']
    if model:
        cmd += ["-m", model]
    for d in add_dirs:
        cmd += ["--add-dir", d]
    return cmd + ["-"]  # the prompt comes on stdin


def run(prompt: str, *, schema: dict, cwd: str, add_dirs: list[str], model: str = "", api_key: str | None = None,
        on_line=lambda line: None, **_) -> Result:
    exe = shutil.which("codex")
    if not exe:
        raise ToolMissing("codex (OpenAI Codex CLI) not found on PATH", "Install it (npm install -g @openai/codex) and sign in with `codex login`.")
    env = dict(os.environ)
    if api_key:
        env["CODEX_API_KEY"] = api_key
    res, t0 = Result(), time.monotonic()
    with tempfile.TemporaryDirectory() as tmp:
        schema_file = os.path.join(tmp, "schema.json")
        with open(schema_file, "w") as f:
            json.dump(strict(schema), f)
        proc = subprocess.Popen(command(exe, schema_file, cwd, add_dirs, model), cwd=cwd, env=env,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
            for line in proc.stdout:
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    if line.strip():
                        res.other_output.append(line.strip())
                    continue
                parse_event(ev, res, on_line)
                if res.limited:
                    interrupt(proc)
            proc.wait()
        except KeyboardInterrupt:
            try:
                proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                proc.terminate()
            raise
    res.duration_ms = int((time.monotonic() - t0) * 1000)  # Codex doesn't report it
    if res.limited:
        exc = UsageLimit(f"Codex usage limit reached: {res.error}")
        exc.result = res
        raise exc
    if not res.ok and not res.error:
        res.error = ("\n".join(res.other_output[-5:]) or f"codex exited with code {proc.returncode}")[:500]
    return res


def check() -> tuple[bool, str]:
    exe = shutil.which("codex")
    if not exe:
        return False, "Not installed. Install it with `npm install -g @openai/codex`, then run `codex login`."
    proc = subprocess.run([exe, "login", "status"], capture_output=True, text=True)
    text = (proc.stdout + proc.stderr).strip().splitlines()
    if proc.returncode == 0:
        return True, text[-1] if text else "Signed in."
    return False, "Installed, but not signed in. Run `codex login` in a terminal, or save an OpenAI API key."
