"""Find ideas (things to do), learnings (things understood) and events (things that happened or will happen)
across finished notes, and commit each batch.

One pass looks for all three kinds, so the same Claude call can link them to each other.
Each kind has its own folder (set in [vault]) and file prefix: idea-*.md, learning-*.md and event-*.md.
"""

import hashlib
import json
import re
import shutil
from datetime import date, timedelta
from pathlib import Path

from . import brain, db, notefile, notes
from .ai import claude_cli
from .config import DATA, brain_dir, load, vault_rel
from .paths import RESOURCES
from .errors import AgentFailed, UsageLimit

REPORT_SCHEMA = {"type": "object", "properties": {
    key: {"type": "array", "items": {"type": "string"}}
    for key in ("created", "updated", "considered", "notes")},
    "required": ["created", "updated", "considered", "notes"]}


# Each kind and its [vault] folder setting.
KINDS = {"idea": "ideas", "learning": "learnings", "event": "events"}
# Per kind: the posts column set once a note was checked for it, and the name its post ids go under
# in a batch row and in a dry-run manifest ("considered" is the ideas check, from before the others existed).
CHECKS = {"idea": ("ideas_checked_at", "considered"), "learning": ("learnings_checked_at", "learned"),
          "event": ("events_checked_at", "events_seen")}
# The runs counters: ideas_created, ideas_updated, learnings_created, …
COUNTERS = tuple(f"{kind}s_{action}" for kind in KINDS for action in ("created", "updated"))


def kind_dir(kind: str) -> Path:
    return brain_dir() / vault_rel(KINDS[kind])


def ideas_dir() -> Path:
    return kind_dir("idea")


def kind_of(name: str) -> str | None:
    """'idea-try-x' → 'idea', 'learning-y.md' → 'learning', 'event-z' → 'event', anything else → None."""
    prefix = Path(name).name.split("-", 1)[0]
    return prefix if prefix in KINDS and "-" in Path(name).name else None


def themes() -> dict[str, list[str]]:
    """Read only the theme index's Posts by theme section."""
    path = brain_dir() / vault_rel("hub")
    if not path.is_file():
        return {}
    found, inside, current = {}, False, None
    for line in path.read_text().splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = line.strip() == "## Posts by theme"
        elif inside and line.startswith("### "):
            current = line[4:].strip()
            found[current] = []
        elif inside and current and (match := re.match(r"- \[\[([^\]|#]+)", line)):
            found[current].append(match.group(1))
    return found


def candidates_new(con, conn_ids=None, cfg=None) -> list[str]:
    """Notes new since `[ideas] since` not yet checked for ideas, then notes of any age not yet checked
    for learnings or events: so Extract also works through older notes for those, batch by batch."""
    since = (cfg or load())["ideas"]["since"]
    sql = ("SELECT p.id FROM posts p WHERE p.status = 'done' AND p.note_path IS NOT NULL"
           " AND ((p.ideas_checked_at IS NULL AND substr(p.updated_at, 1, 10) >= ?)"
           " OR p.learnings_checked_at IS NULL OR p.events_checked_at IS NULL)")
    args = [since]
    if conn_ids is not None:
        if not conn_ids:
            return []
        sql += (f" AND EXISTS (SELECT 1 FROM connection_posts cp WHERE cp.post_id = p.id"
                f" AND cp.connection_id IN ({db.placeholders(conn_ids)}))")
        args.extend(conn_ids)
    # New notes (due for ideas) first, then the older ones waiting only for learnings or events.
    order = " ORDER BY NOT (p.ideas_checked_at IS NULL AND substr(p.updated_at, 1, 10) >= ?), p.rowid"
    return [r[0] for r in con.execute(sql + order, args + [since])]


def candidates_rebuild(con, chosen: list[str] | None) -> list[str]:
    """Unchecked notes listed under the chosen themes (all themes if None), any date."""
    mapping = themes()
    unknown = set(chosen or []) - set(mapping)
    if unknown:
        raise ValueError(f"Unknown themes: {', '.join(sorted(unknown))}. Known themes: {', '.join(mapping)}")
    names = {name for theme in (chosen if chosen is not None else mapping) for name in mapping[theme]}
    return [r["id"] for r in con.execute("SELECT id, note_path FROM posts WHERE status = 'done' AND note_path IS NOT NULL"
                                           f" AND ({unchecked_sql()}) ORDER BY rowid")
            if Path(r["note_path"]).stem in names]


def _source_names(value) -> list[str]:
    if not isinstance(value, list):
        return []
    names = []
    for item in value:
        if isinstance(item, list):
            item = item[0] if item else ""
        if isinstance(item, str):
            names.append(item.strip().removeprefix("[[").removesuffix("]]").split("|")[0].split("#")[0])
    return [name for name in names if name]


def _file_path(item: str, folder: Path) -> Path | None:
    """A reported file as an existing path inside `folder`, whether Claude gave it absolute,
    relative to the vault, or as a bare file name."""
    path = Path(item).expanduser()
    tries = [path] if path.is_absolute() else [brain_dir() / path, folder / path.name]
    for p in (t.resolve() for t in tries):
        if p.is_relative_to(folder.resolve()) and p.is_file():
            return p
    return None


def _sha(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def dry_run_dir(run_id) -> Path:
    return DATA / "ideas-dry-run" / f"run-{run_id}"


def read_manifest(folder: Path) -> dict:
    """What a dry run saw and did: the existing ideas' fingerprints and the posts it considered."""
    path = folder / "manifest.json"
    return json.loads(path.read_text()) if path.is_file() else {}


def unchecked_sql(kinds=KINDS) -> str:
    """'ideas_checked_at IS NULL OR …': a note still to check for any of `kinds`."""
    return " OR ".join(f"{CHECKS[kind][0]} IS NULL" for kind in kinds)


def note_files(folder: Path) -> list[Path]:
    """Idea, learning and event files directly inside `folder` (a dry run keeps the kinds side by side)."""
    return sorted(p for kind in KINDS for p in folder.glob(f"{kind}-*.md"))


def _checks(con, ids) -> dict[str, dict]:
    """Which checks each post still needs: {'idea': bool, 'learning': bool, 'event': bool}."""
    columns = ", ".join(column for column, _ in CHECKS.values())
    rows = con.execute(f"SELECT id, {columns} FROM posts WHERE id IN ({db.placeholders(ids)})", list(ids)) if ids else []
    return {r["id"]: {kind: r[column] is None for kind, (column, _) in CHECKS.items()} for r in rows}


def _mark(con, checked: dict[str, list]) -> None:
    """Mark posts checked, per kind: {'idea': [post ids], 'learning': [...], 'event': [...]}."""
    stamp = db.now()
    for kind, ids in checked.items():
        column = CHECKS[kind][0]
        con.executemany(f"UPDATE posts SET {column} = ? WHERE id = ? AND {column} IS NULL", [(stamp, pid) for pid in ids])
    con.commit()


def look_for(needs: dict) -> str:
    """What the prompt asks for in a note: 'ideas, learnings and events', 'learnings and events', …"""
    wanted = [f"{kind}s" for kind in KINDS if needs.get(kind)] or ["learnings", "events"]
    return ", ".join(wanted[:-1]) + " and " + wanted[-1] if len(wanted) > 1 else wanted[0]


def counts(result: dict) -> dict:
    """A pass result as the runs counters: {'ideas_created': 2, …, 'events_updated': 0}."""
    return {key: len(result.get(key.removeprefix("ideas_"), [])) for key in COUNTERS}  # ideas use "created" and "updated"


def apply_dry_run(con, run_id: int, report, apply_run_id: int | None = None) -> dict:
    """Copy a reviewed dry run into the brain and mark its notes checked, without calling Claude again.

    An item the user changed (or deleted) after the dry run is skipped, so their edits are never overwritten.
    """
    folder = dry_run_dir(run_id)
    manifest = read_manifest(folder)
    if not manifest:
        raise ValueError(f"run {run_id} has no dry-run results to apply")
    if manifest.get("applied"):
        raise ValueError(f"dry run {run_id} was already applied ({manifest['applied']})")
    base = manifest.get("base", {})
    before = brain.snapshot()
    copied, skipped = [], []
    counts = dict.fromkeys(COUNTERS, 0)
    for src in note_files(folder):
        target = kind_dir(kind_of(src.name))
        target.mkdir(parents=True, exist_ok=True)
        dst = target / src.name
        current = _sha(dst) if dst.is_file() else None
        if current != base.get(src.name):
            skipped.append(src.name)
            report(f"skipped {src.name}: changed in the vault after the dry run", level="warn")
            continue
        shutil.copyfile(src, dst)
        copied.append(src.name)
        counts[f"{kind_of(src.name)}s_{'updated' if current else 'created'}"] += 1
        report(f"{'updated' if current else 'created'} {kind_of(src.name)} {src.name}")
    # Older dry runs list only "considered" (checked for ideas), or no events.
    needs = _checks(con, {pid for _, key in CHECKS.values() for pid in manifest.get(key, [])})
    checked = {kind: [pid for pid in manifest.get(key, []) if needs.get(pid, {}).get(kind)] for kind, (_, key) in CHECKS.items()}
    _mark(con, checked)
    sha, changed = brain.finish(before, brain.idea_paths(), f"agent: ideas, learnings and events from dry run {run_id}")
    if sha:
        report(f"vault commit {sha}: {len(changed)} files")
    notes.add_commit(con, apply_run_id, sha)
    db.add_batch(con, apply_run_id, "apply", 1, post_ids=[str(run_id)], considered=checked["idea"],
                 learned=checked["learning"], events_seen=checked["event"])
    manifest["applied"] = sha or "nothing to commit"
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return {"copied": copied, "skipped": skipped, "counts": counts, "commit": sha,
            **{key: checked[kind] for kind, (_, key) in CHECKS.items()}}


def _known(kind: str, folder: Path | None) -> list[dict]:
    """The existing items of a kind; in a dry run its own proposals stand in for the brain's copies."""
    items = list_items(kind)
    if folder is not None:
        items = list({i["name"]: i for i in items + list_items(kind, folder)}.values())
    return items


def run_pass(con, post_ids, cfg, report, run_id=None, dry_run=False, api_key=None) -> dict:
    """Run one Claude call per batch and keep finished work on a usage limit."""
    size = max(1, int(cfg["ideas"]["batch_size"]))
    batches = [post_ids[i:i + size] for i in range(0, len(post_ids), size)]
    result = {"created": [], "updated": [], "considered": []} | {key: [] for key in COUNTERS if not key.startswith("ideas_")}
    folder = dry_run_dir(run_id) if dry_run else None
    if dry_run:
        folder.mkdir(parents=True, exist_ok=True)
        manifest = read_manifest(folder) or {
            "run_id": run_id, "base": {p.name: _sha(p) for kind in KINDS for p in kind_dir(kind).glob(f"{kind}-*.md")}}
        for _, key in CHECKS.values():
            manifest.setdefault(key, [])
    else:
        for kind in KINDS:
            kind_dir(kind).mkdir(parents=True, exist_ok=True)
    for n, batch in enumerate(batches, start=1):
        report(f"ideas batch {n}/{len(batches)}: {' '.join(batch)}")
        before = brain.snapshot()  # in a dry run too: proves the brain was left alone
        rows = con.execute(f"SELECT id, note_path FROM posts WHERE id IN ({db.placeholders(batch)})", batch)
        paths = {r["id"]: r["note_path"] for r in rows}
        needs = _checks(con, batch)
        mode = ("This is a dry run. Write every idea, learning and event you would create or update into "
                f"{folder}. For updates, write a full copy under the existing file name. Change nothing in {brain_dir()}."
                if dry_run else f"Write ideas into {ideas_dir()}, learnings into {kind_dir('learning')}"
                                f" and events into {kind_dir('event')}.")
        # Re-read every batch: the previous batch may have created or updated some.
        known = {kind: _known(kind, folder) for kind in KINDS}
        prompt = notes.render("ideas.md", count=len(batch),
                              notes="\n".join(f"{pid}  {paths.get(pid) or ''}  [{look_for(needs.get(pid, {}))}]" for pid in batch),
                              today=date.today().isoformat(), ideas_dir=folder or ideas_dir(),
                              learnings_dir=folder or kind_dir("learning"), events_dir=folder or kind_dir("event"), mode=mode,
                              max_new=cfg["ideas"]["max_new_per_pass"],
                              max_new_learnings=cfg["ideas"].get("max_new_learnings_per_pass", 8),
                              max_new_events=cfg["ideas"].get("max_new_events_per_pass", 8),
                              existing_count=len(known["idea"]), existing=catalog(known["idea"]),
                              existing_learnings_count=len(known["learning"]), existing_learnings=catalog(known["learning"]),
                              existing_events_count=len(known["event"]), existing_events=catalog(known["event"]))
        limit = None
        try:
            res = claude_cli.run(prompt, schema=REPORT_SCHEMA, cwd=str(brain_dir(cfg)),
                                 add_dirs=[str(RESOURCES)] + ([str(folder)] if dry_run else []),
                                 model=cfg["ideas"]["model"], backend=cfg["notes"]["backend"], api_key=api_key,
                                 max_budget_usd=cfg["notes"].get("max_budget_usd_per_batch"),
                                 on_line=lambda line: report(f"  {line}"))
        except UsageLimit as exc:
            limit, res = exc, getattr(exc, "result", None)
        notes.add_usage(con, run_id, res)
        if res:
            report(f"ideas batch {n} usage: {notes.describe_usage(res)}")
        structured = (res.structured or {}) if res else {}
        batch_counts = dict.fromkeys(COUNTERS, 0)
        names = notefile.brain_names()
        for key in ("created", "updated"):
            for item in structured.get(key, []):
                kind = kind_of(item)
                path = _file_path(item, folder or kind_dir(kind)) if kind else None
                if path is None:
                    report(f"reported {key} file is not an idea, learning or event in its folder, or is missing: {item}", level="warn")
                    continue
                result[key if kind == "idea" else f"{kind}s_{key}"].append(str(path))
                batch_counts[f"{kind}s_{key}"] += 1
                report(f"{key} {kind} {path.name}")
                meta = notefile.read(path, head_only=True).meta
                for field in ("description", "support", "sources") + (("when",) if kind == "event" else ()):
                    if not meta.get(field):
                        report(f"{path.name}: missing {field} front matter", level="warn")
                for source in _source_names(meta.get("sources")):
                    if source not in names:
                        report(f"{path.name}: source [[{source}]] has no note", level="warn")
        for remark in structured.get("notes", []):
            report(f"  {remark}")
        considered = set(structured.get("considered", [])) & set(batch)
        result["considered"].extend(pid for pid in batch if pid in considered)
        checked = {kind: [pid for pid in batch if pid in considered and needs.get(pid, {}).get(kind)] for kind in KINDS}
        if dry_run:
            for kind, (_, key) in CHECKS.items():
                manifest[key] += checked[kind]
            (folder / "manifest.json").write_text(json.dumps(manifest, indent=1))
            touched = brain.changed_since(before, ("",))
            if touched:  # never committed; the user decides what to keep
                report(f"brain files changed during the dry run (by the agent, or by you in Obsidian; nothing was committed): {', '.join(touched)}", level="error")
        else:
            _mark(con, checked)
            sha, changed = brain.finish(before, brain.idea_paths(),
                                                   f"agent: ideas pass {n} (run {run_id})")
            notes.add_commit(con, run_id, sha)
            if sha:
                report(f"vault commit {sha}: {len(changed)} files")
        saved = {} if dry_run else checked
        db.add_batch(con, run_id, "ideas", n, batch, considered=saved.get("idea", ()), learned=saved.get("learning", ()),
                     events_seen=saved.get("event", ()), res=res, error=limit)
        if run_id:
            con.execute("UPDATE runs SET " + ", ".join(f"{k} = {k} + ?" for k in batch_counts) + " WHERE id = ?",
                        (*batch_counts.values(), run_id))
            con.commit()
        if limit:
            raise limit
        if res and not res.ok:
            raise AgentFailed(f"ideas pass failed in batch {n}: {res.error}")
        stop_at = float(cfg["notes"].get("stop_at_plan_usage") or 0)
        fh = notes.five_hour(res.plan if res else None)
        if cfg["notes"]["backend"] == "subscription" and stop_at and fh is not None and fh >= stop_at and n < len(batches):
            raise UsageLimit(f"Plan 5-hour window is {fh:.0%} used; stopping before the next batch"
                             f"{claude_cli.resets((res.plan or {}).get('unifiedWindows', {}).get('five_hour'))}")
    return result


def catalog(items: list[dict]) -> str:
    """One line per existing item of a kind, for the prompt: enough to compare a candidate with all of them.
    Events also give their date, so the same happening is recognised even under another name."""
    if not items:
        return "(none yet)"
    return "\n".join(f"- {i['name']}.md · {i['title']} · " + (f"{i['when'] or 'no date'} · " if i["kind"] == "event" else "")
                     + f"{i['description'] or '—'} · {i['status']} · "
                     + (", ".join(i["sources"]) or "no sources") for i in sorted(items, key=lambda i: i["name"]))


DATE = re.compile(r"\d{4}(-\d{2}(-\d{2})?)?")


def event_timing(when: str, until: str = "", today: date | None = None) -> str:
    """'upcoming' until the event's last day has passed, then 'past'; 'undated' without a usable date.

    A date known only by month or year ('2026-10', '1983') is upcoming only until that period begins:
    news "from October" read in October has most likely happened already.
    """
    end = until if DATE.fullmatch(until or "") else when
    if not DATE.fullmatch(end or ""):
        return "undated"
    now = (today or date.today()).isoformat()[:len(end)]
    return "upcoming" if end > now or (end == now and len(end) == 10) else "past"


def _sort_events(items: list[dict]) -> list[dict]:
    """Coming up first (soonest first), then past (most recent first), then those without a date."""
    upcoming = sorted((i for i in items if i["timing"] == "upcoming"), key=lambda i: i["when"])
    past = sorted((i for i in items if i["timing"] == "past"), key=lambda i: i["until"] or i["when"], reverse=True)
    return upcoming + past + [i for i in items if i["timing"] == "undated"]


def calendar_file(item: dict) -> str | None:
    """An iCalendar file for an upcoming event with a full date, so it can be added to a calendar."""
    if item["timing"] != "upcoming" or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", item["when"]):
        return None
    last = item["until"] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", item["until"] or "") else item["when"]
    day = lambda value: value.replace("-", "")
    text = lambda value: re.sub(r"([,;\\])", r"\\\1", str(value)).replace("\n", " ")
    end = (date.fromisoformat(last) + timedelta(days=1)).isoformat()  # DTEND is the day after the last day
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//rot2gold//events//EN", "BEGIN:VEVENT",
             f"UID:{item['name']}@rot2gold", f"DTSTAMP:{date.today().strftime('%Y%m%d')}T000000Z",
             f"DTSTART;VALUE=DATE:{day(item['when'])}", f"DTEND;VALUE=DATE:{day(end)}", f"SUMMARY:{text(item['title'])}"]
    if item["where"]:
        lines.append(f"LOCATION:{text(item['where'])}")
    lines += ["DESCRIPTION:" + "\\n\\n".join(text(part) for part in (item["description"],
              "From your saved videos: check the date before relying on it.") if part), "END:VEVENT", "END:VCALENDAR"]
    # Long lines are folded: a line break and a space every 60 characters (the limit is 75 bytes).
    return "".join("\r\n ".join(line[i:i + 60] for i in range(0, len(line), 60)) + "\r\n" for line in lines)


def list_items(kind: str, folder=None) -> list[dict]:
    out = []
    for path in (folder or kind_dir(kind)).glob(f"{kind}-*.md"):
        note = notefile.read(path, head_only=True)
        meta = note.meta
        sources = _source_names(meta.get("sources"))
        try:
            support = int(meta.get("support", len(sources)))
        except (ValueError, TypeError):
            support = len(sources)
        item = {"name": path.stem, "kind": kind, "path": path, "title": note.title,
                "description": meta.get("description", ""), "status": meta.get("status", "new"),
                "support": support, "created": str(meta.get("created", "")),
                "updated": str(meta.get("updated", "")), "sources": sources,
                "tags": meta.get("tags", [])}
        if kind == "event":
            when, until = (str(meta.get(f) or "").strip() for f in ("when", "until"))
            item |= {"when": when, "until": until, "where": str(meta.get("where") or "").strip(),
                     "timing": event_timing(when, until)}
        out.append(item)
    if kind == "event":
        return _sort_events(out)
    return sorted(out, key=lambda x: (x["support"], x["updated"]), reverse=True)


def list_ideas(folder=None) -> list[dict]:
    return list_items("idea", folder)


def list_learnings(folder=None) -> list[dict]:
    return list_items("learning", folder)


def list_events(folder=None) -> list[dict]:
    return list_items("event", folder)
