"""Run Claude Code non-interactively (`claude -p`) and read its event stream.

Two backends, same agent loop, tools and prompts:
- subscription: the user's Claude plan login. ANTHROPIC_API_KEY is removed from the child's environment,
  because Claude Code prefers a key over the plan login when both exist.
- api: the same tools, including web tools; the key is set only in the child's environment.
  Bare mode would remove WebSearch and WebFetch, which note writing needs.
"""

import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime

from ..errors import AgentFailed, ToolMissing, UsageLimit
from .base import Result, interrupt, is_limit

ALLOWED_TOOLS = ["Read", "Write", "Edit", "Glob", "Grep", "WebSearch", "WebFetch",
                 "Bash(r2g pending *)", "Bash(r2g done *)", "Bash(r2g skip *)", "Bash(rg *)", "Bash(find *)"]


def describe_tool(block: dict) -> str | None:
    """One short line for the run log, or None for calls not worth showing."""
    name, inp = block.get("name"), block.get("input") or {}
    if name == "Bash":
        cmd = inp.get("command", "")
        return cmd if cmd.startswith(("r2g done", "r2g skip", "r2g pending")) else None
    if name in ("Write", "Edit"):
        return f"{name.lower()} {os.path.basename(inp.get('file_path', ''))}"
    if name == "WebSearch":
        return f"search: {inp.get('query', '')[:80]}"
    if name == "WebFetch":
        return f"open: {inp.get('url', '')[:80]}"
    return None


def parse_event(ev: dict, res: Result, on_line) -> None:
    t = ev.get("type")
    if t == "assistant":
        for block in ev.get("message", {}).get("content", []):
            if block.get("type") == "tool_use" and (line := describe_tool(block)):
                on_line(line)
    elif t == "rate_limit_event":
        info = ev.get("rate_limit_info") or {}
        res.plan = info
        if info.get("status") not in (None, "allowed", "allowed_warning"):
            res.limited = True
    elif t == "system" and ev.get("subtype") == "api_retry" and ev.get("error") == "rate_limit":
        on_line(f"rate limited, retry {ev.get('attempt')}/{ev.get('max_retries')}")
        if (ev.get("attempt") or 0) >= 3:
            res.limited = True
    elif t == "result":
        res.ok = ev.get("subtype") == "success" and not ev.get("is_error")
        res.text = ev.get("result") or ""
        res.structured = ev.get("structured_output")
        res.turns = ev.get("num_turns") or 0
        res.duration_ms = ev.get("duration_ms") or 0
        res.cost_usd = ev.get("total_cost_usd") or 0.0
        u = ev.get("usage") or {}
        res.usage = {"tokens_in": u.get("input_tokens", 0), "tokens_out": u.get("output_tokens", 0),
                     "cache_read": u.get("cache_read_input_tokens", 0),
                     "cache_write": u.get("cache_creation_input_tokens", 0)}
        if not res.ok:
            res.error = res.text or ev.get("subtype", "error")
            if is_limit(res.error):
                res.limited = True


def run(prompt: str, *, schema: dict, cwd: str, add_dirs: list[str], model: str = "",
        backend: str = "subscription", api_key: str | None = None, max_budget_usd: float | None = None,
        on_line=lambda line: None, allowed_tools: list[str] | None = None) -> Result:
    exe = shutil.which("claude")
    if not exe:
        raise ToolMissing("claude (Claude Code) not found on PATH", "Install Claude Code and log in with `claude`.")
    cmd = [exe, "-p", "--output-format", "stream-json", "--verbose",
           "--json-schema", json.dumps(schema), "--permission-prompts", "none", "--permission-mode", "dontAsk",
           "--no-session-persistence", "--strict-mcp-config"]
    if model:  # empty: Claude Code's own default
        cmd += ["--model", model]
    tools = ALLOWED_TOOLS if allowed_tools is None else allowed_tools
    if tools:  # an empty --allowedTools would swallow the next flag
        cmd += ["--allowedTools", *tools]
    for d in add_dirs:
        cmd += ["--add-dir", d]
    env = dict(os.environ)
    if backend == "api":
        if not api_key:
            raise AgentFailed("API backend selected but no API key is set", "Set it in Settings, or switch to the subscription.")
        env["ANTHROPIC_API_KEY"] = api_key
        if max_budget_usd:
            cmd += ["--max-budget-usd", str(max_budget_usd)]
    else:
        env.pop("ANTHROPIC_API_KEY", None)

    res = Result()
    # stderr joins stdout: a separate pipe could fill up and block claude while we read stdout.
    proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1)
    try:
        proc.stdin.write(prompt)  # the prompt goes on stdin, not the command line
        proc.stdin.close()
        for line in proc.stdout:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                if line.strip():
                    res.other_output.append(line.strip())
                continue
            parse_event(ev, res, on_line)
            if res.limited and ev.get("type") != "result":
                interrupt(proc)  # stop politely; the turn ends and a result follows
        proc.wait()
    except KeyboardInterrupt:
        # Stop pressed (SIGINT reaches the whole process group): let claude end its turn, then give up.
        try:
            proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            proc.terminate()
        raise
    if res.limited:
        exc = UsageLimit(f"Claude usage limit reached{resets(res.plan)}")
        exc.result = res  # usage of the partial batch still counts
        raise exc
    if not res.ok and not res.error:
        res.error = ("\n".join(res.other_output[-5:]) or f"claude exited with code {proc.returncode}")[:500]
    return res


def test_key(api_key: str) -> Result:
    """Make a cheap tool-free call in an isolated directory to check key billing."""
    with tempfile.TemporaryDirectory() as cwd:
        return run("Reply with ok", schema={"type": "object", "properties": {"ok": {"type": "boolean"}},
                                            "required": ["ok"]}, cwd=cwd, add_dirs=[], model="haiku",
                   backend="api", api_key=api_key, max_budget_usd=0.05, allowed_tools=[])


def resets(plan: dict | None) -> str:
    """' (resets 15:00)' from rate_limit_info, if known."""
    ts = (plan or {}).get("resetsAt")
    return f" (resets {datetime.fromtimestamp(ts).strftime('%H:%M')})" if ts else ""
