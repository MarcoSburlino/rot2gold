"""Note writing: one `claude -p` per batch of processed posts, then index and commit in the brain.

The agent follows prompts/write-notes.md (which points to docs/note-writing.md) and marks each post
with `vn done` or `vn skip`. The app, not the agent, runs brain-index and commits.
"""

import json
from datetime import date

from . import brain, db
from .ai import claude_cli
from .config import PROMPTS, ROOT, brain_dir
from .errors import AgentFailed, UsageLimit
from .events import echo

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "posts": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"},
            "note_path": {"type": ["string", "null"]},
            "skip_reason": {"type": ["string", "null"]},
        }, "required": ["id"]}},
        "new_tags": {"type": "array", "items": {"type": "string"}},
        "disputed": {"type": "array", "items": {"type": "string"}},
        "problems": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["posts", "new_tags", "disputed", "problems"],
}


def render(name: str, **values) -> str:
    text = (PROMPTS / name).read_text()
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text


def add_usage(con, run_id: int | None, res: claude_cli.Result) -> None:
    if run_id is None or res is None:
        return
    u = res.usage
    con.execute("UPDATE runs SET tokens_in = tokens_in + ?, tokens_out = tokens_out + ?, cache_read = cache_read + ?,"
                " cache_write = cache_write + ?, cost_estimate_usd = cost_estimate_usd + ?,"
                " plan_usage = COALESCE(?, plan_usage) WHERE id = ?",
                (u["tokens_in"], u["tokens_out"], u["cache_read"], u["cache_write"], res.cost_usd,
                 json.dumps(res.plan) if res.plan else None, run_id))
    con.commit()


def add_commit(con, run_id: int | None, sha: str | None) -> None:
    if run_id and sha:
        con.execute("UPDATE runs SET brain_commits = TRIM(COALESCE(brain_commits, '') || ' ' || ?) WHERE id = ?",
                    (sha, run_id))
        con.commit()


def five_hour(plan: dict | None) -> float | None:
    return (((plan or {}).get("unifiedWindows") or {}).get("five_hour") or {}).get("utilization")


def describe_usage(res: claude_cli.Result) -> str:
    u = res.usage
    line = (f"{res.turns} turns, {res.duration_ms / 60000:.1f} min, {u['cache_read'] / 1e6:.1f} M cache-read tokens,"
            f" {u['tokens_out'] / 1e3:.0f} k output, ~${res.cost_usd:.2f} API-equivalent")
    if (fh := five_hour(res.plan)) is not None:
        line += f"; plan 5-hour window {fh:.0%} used"
    return line


def check_batch(con, batch: list[str], report) -> tuple[int, int]:
    """Every post must now be done (with an existing note) or skipped. Returns (noted, skipped)."""
    noted = skipped = 0
    for pid in batch:
        row = con.execute("SELECT status, note_path, skip_reason FROM posts WHERE id = ?", (pid,)).fetchone()
        if row["status"] == "done":
            path = brain.note_file(row["note_path"] or "")
            if not path.is_file():
                db.set_status(con, pid, "processed", note_path=None)
                report(f"{pid}: marked done but {row['note_path']} is missing; it will be retried", post_id=pid, level="warn")
            elif f'post_id: "{pid}"' not in path.read_text():
                noted += 1
                report(f"{pid}: noted as {row['note_path']}, but its post_id front matter doesn't match", post_id=pid, level="warn")
            else:
                noted += 1
                report(f"noted {pid} → {row['note_path']}", post_id=pid)
        elif row["status"] == "skipped":
            skipped += 1
            report(f"skipped {pid}: {row['skip_reason']}", post_id=pid)
        else:
            report(f"{pid}: not finished in this batch; it will be retried", post_id=pid, level="warn")
    return noted, skipped


def write_notes(con, ids: list[str], cfg: dict, report=echo, run_id: int | None = None, api_key=None) -> tuple[int, int]:
    """Write notes for `ids` (processed posts) in batches. Returns (noted, skipped)."""
    ncfg = cfg["notes"]
    size = max(1, int(ncfg["batch_size"]))
    batches = [ids[i:i + size] for i in range(0, len(ids), size)]
    noted = skipped = 0
    for n, batch in enumerate(batches, start=1):
        report(f"batch {n}/{len(batches)}: {' '.join(batch)}")
        before = brain.snapshot()
        prompt = render("write-notes.md", ids="\n".join(batch), count=len(batch), today=date.today().isoformat())
        limit = None
        try:
            res = claude_cli.run(prompt, schema=REPORT_SCHEMA, cwd=str(ROOT), add_dirs=[str(brain_dir(cfg))],
                                 model=ncfg["model"], backend=ncfg["backend"], api_key=api_key,
                                 max_budget_usd=ncfg.get("max_budget_usd_per_batch"),
                                 on_line=lambda line: report(f"  {line}"))
        except UsageLimit as exc:
            limit, res = exc, getattr(exc, "result", None)
        add_usage(con, run_id, res)
        if res:
            report(f"batch {n} usage: {describe_usage(res)}")
            for key, label in (("new_tags", "new tag"), ("disputed", "disputed"), ("problems", "problem")):
                for item in (res.structured or {}).get(key, []):
                    report(f"  {label}: {item}", level="warn" if key == "problems" else "info")
        b_noted, b_skipped = check_batch(con, batch, report)
        noted, skipped = noted + b_noted, skipped + b_skipped
        # Commit whatever the batch finished, even if it was cut short.
        sha, paths = brain.index_and_commit(before, brain.NOTE_PATHS, f"agent: video notes batch {n} (run {run_id})")
        add_commit(con, run_id, sha)
        if sha:
            report(f"brain commit {sha}: {len(paths)} files")
        if limit:
            raise limit
        if res and not res.ok:
            raise AgentFailed(f"note writing failed in batch {n}: {res.error}")
        stop_at = float(ncfg.get("stop_at_plan_usage") or 0)
        fh = five_hour(res.plan if res else None)
        if ncfg["backend"] == "subscription" and stop_at and fh is not None and fh >= stop_at and n < len(batches):
            raise UsageLimit(f"Plan 5-hour window is {fh:.0%} used; stopping before the next batch"
                             f"{claude_cli.resets((res.plan or {}).get('unifiedWindows', {}).get('five_hour'))}")
    return noted, skipped
