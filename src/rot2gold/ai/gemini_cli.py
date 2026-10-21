"""Run Google's Gemini CLI non-interactively (`gemini -p --output-format stream-json`) and read its events.

It works like Claude Code here: file tools in the vault, web search, and `r2g`. A policy file allows
exactly those tools; in headless mode anything else needs approval, which counts as a refusal.
Gemini CLI has no JSON-schema flag, so the prompt asks for the report as JSON and the app checks it.
Login: the user's Google account (run `gemini` once), or a Gemini API key from the keychain.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..errors import ToolMissing, UsageLimit
from .base import Result, interrupt, is_limit, json_from_text, missing

POLICY = """\
[[rule]]
toolName = ["read_file", "read_many_files", "write_file", "replace", "glob", "grep_search", "search_file_content",
            "list_directory", "google_web_search", "web_fetch", "write_todos"]
decision = "allow"
priority = 900

[[rule]]
toolName = "run_shell_command"
commandPrefix = ["r2g pending", "r2g done", "r2g skip", "rg "]
decision = "allow"
priority = 900
"""


def describe_tool(name: str, args: dict) -> str | None:
    if name == "run_shell_command":
        cmd = args.get("command", "")
        return cmd if cmd.startswith(("r2g done", "r2g skip", "r2g pending")) else None
    if name in ("write_file", "replace"):
        return f"{'write' if name == 'write_file' else 'edit'} {os.path.basename(args.get('file_path', ''))}"
    if name == "google_web_search":
        return f"search: {args.get('query', '')[:80]}"
    if name == "web_fetch":
        return f"open: {args.get('prompt', args.get('url', ''))[:80]}"
    return None


def parse_event(ev: dict, res: Result, on_line, answer: list) -> None:
    """`answer` collects the assistant's text since its last tool call: the report is at the end."""
    t = ev.get("type")
    if t == "message" and ev.get("role") == "assistant":
        answer.append(ev.get("content") or "")
    elif t == "tool_use":
        answer.clear()
        res.turns += 1
        if (line := describe_tool(ev.get("tool_name", ""), ev.get("parameters") or {})):
            on_line(line)
    elif t == "error":
        res.other_output.append(str(ev.get("message", ""))[:300])
    elif t == "result":
        stats = ev.get("stats") or {}
        res.duration_ms = stats.get("duration_ms") or 0
        res.usage = {"tokens_in": stats.get("input_tokens", 0), "tokens_out": stats.get("output_tokens", 0),
                     "cache_read": stats.get("cached", 0), "cache_write": 0}
        res.text = "".join(answer)
        if ev.get("status") == "success":
            res.structured = json_from_text(res.text)
            res.ok = res.structured is not None
            if not res.ok:
                res.error = "Gemini finished without the JSON report: " + res.text[-300:]
        else:
            res.error = str((ev.get("error") or {}).get("message") or "Gemini failed")[:500]
            res.limited = is_limit(res.error)


def run(prompt: str, *, schema: dict, cwd: str, add_dirs: list[str], model: str = "", api_key: str | None = None,
        on_line=lambda line: None, **_) -> Result:
    exe = shutil.which("gemini")
    if not exe:
        raise ToolMissing("gemini (Gemini CLI) not found on PATH", "Install it (npm install -g @google/gemini-cli) and sign in by running `gemini` once.")
    env = dict(os.environ)
    if api_key:
        env["GEMINI_API_KEY"] = api_key
    prompt += ("\n\nWhen you have finished, end your answer with the report: only a JSON object, no other text,"
               f" matching this JSON Schema:\n{json.dumps(schema)}\n")
    res, answer = Result(), []
    with tempfile.TemporaryDirectory() as tmp:
        policy = Path(tmp) / "rot2gold.toml"
        policy.write_text(POLICY)
        cmd = [exe, "-p", "Follow the instructions above.", "--output-format", "stream-json", "--skip-trust",
               "--approval-mode", "default", "--policy", str(policy)]
        if add_dirs:
            cmd += ["--include-directories", ",".join(add_dirs)]
        if model:
            cmd += ["-m", model]
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1)
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
                parse_event(ev, res, on_line, answer)
                if res.limited:
                    interrupt(proc)
            proc.wait()
        except KeyboardInterrupt:
            try:
                proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                proc.terminate()
            raise
    if res.ok and (gaps := missing(res.structured, schema)):
        res.ok, res.error = False, f"Gemini's report is missing {', '.join(gaps)}"
    if res.limited:
        exc = UsageLimit(f"Gemini usage limit reached: {res.error}")
        exc.result = res
        raise exc
    if not res.ok and not res.error:
        res.error = ("\n".join(res.other_output[-5:]) or f"gemini exited with code {proc.returncode}")[:500]
    return res


def check(api_key: str | None = None) -> tuple[bool, str]:
    if not shutil.which("gemini"):
        return False, "Gemini CLI is not installed. Install it with `npm install -g @google/gemini-cli`, then run `gemini` once to sign in."
    if api_key or os.environ.get("GEMINI_API_KEY"):
        return True, "Gemini API key set."
    if (Path.home() / ".gemini/oauth_creds.json").exists():
        return True, "Signed in with Google."
    return False, "Gemini CLI is installed but not signed in. Run `gemini` once in a terminal, or save a Gemini API key."
