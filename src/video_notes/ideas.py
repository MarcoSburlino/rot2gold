"""Find actionable ideas across finished notes and commit each completed batch."""

import hashlib
import json
import re
import shutil
from datetime import date
from pathlib import Path

from . import brain, db, notefile, notes
from .ai import claude_cli
from .config import DATA, ROOT, brain_dir, load
from .errors import AgentFailed, UsageLimit

REPORT_SCHEMA = {"type": "object", "properties": {
    key: {"type": "array", "items": {"type": "string"}}
    for key in ("created", "updated", "considered", "notes")},
    "required": ["created", "updated", "considered", "notes"]}


def ideas_dir() -> Path:
    return brain_dir() / "Inbox/ideas"


def themes() -> dict[str, list[str]]:
    """Read only the theme index's Posts by theme section."""
    path = brain_dir() / "Resources/commonplace/commonplace.md"
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
    since = (cfg or load())["ideas"]["since"]
    sql = ("SELECT p.id FROM posts p WHERE p.status = 'done' AND p.note_path IS NOT NULL"
           " AND p.ideas_checked_at IS NULL AND substr(p.updated_at, 1, 10) >= ?")
    args = [since]
    if conn_ids is not None:
        if not conn_ids:
            return []
        sql += (f" AND EXISTS (SELECT 1 FROM connection_posts cp WHERE cp.post_id = p.id"
                f" AND cp.connection_id IN ({db.placeholders(conn_ids)}))")
        args.extend(conn_ids)
    return [r[0] for r in con.execute(sql + " ORDER BY p.rowid", args)]


def candidates_rebuild(con, chosen: list[str] | None) -> list[str]:
    """Unchecked notes listed under the chosen themes (all themes if None), any date."""
    mapping = themes()
    unknown = set(chosen or []) - set(mapping)
    if unknown:
        raise ValueError(f"Unknown themes: {', '.join(sorted(unknown))}. Known themes: {', '.join(mapping)}")
    names = {name for theme in (chosen if chosen is not None else mapping) for name in mapping[theme]}
    return [r["id"] for r in con.execute("SELECT id, note_path FROM posts WHERE status = 'done'"
                                           " AND note_path IS NOT NULL AND ideas_checked_at IS NULL ORDER BY rowid")
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
    relative to the brain, relative to the repo, or as a bare file name."""
    path = Path(item).expanduser()
    tries = [path] if path.is_absolute() else [brain_dir() / path, ROOT / path, folder / path.name]
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


def apply_dry_run(con, run_id: int, report) -> dict:
    """Copy a reviewed dry run into Inbox/ideas and mark its notes checked, without calling Claude again.

    An idea Marco changed (or deleted) after the dry run is skipped, so his edits are never overwritten.
    """
    folder = dry_run_dir(run_id)
    manifest = read_manifest(folder)
    if not manifest:
        raise ValueError(f"run {run_id} has no dry-run results to apply")
    if manifest.get("applied"):
        raise ValueError(f"dry run {run_id} was already applied ({manifest['applied']})")
    target, base = ideas_dir(), manifest.get("base", {})
    target.mkdir(parents=True, exist_ok=True)
    before = brain.snapshot()
    copied, skipped = [], []
    for src in sorted(folder.glob("idea-*.md")):
        dst = target / src.name
        current = _sha(dst) if dst.is_file() else None
        if current != base.get(src.name):
            skipped.append(src.name)
            report(f"skipped {src.name}: changed in the brain after the dry run", level="warn")
            continue
        shutil.copyfile(src, dst)
        copied.append(src.name)
        report(f"{'updated' if current else 'created'} idea {src.name}")
    considered = manifest.get("considered", [])
    if considered:
        con.executemany("UPDATE posts SET ideas_checked_at = ? WHERE id = ? AND ideas_checked_at IS NULL",
                        [(db.now(), pid) for pid in considered])
        con.commit()
    sha, changed = brain.index_and_commit(before, brain.IDEA_PATHS, f"agent: ideas from dry run {run_id}")
    if sha:
        report(f"brain commit {sha}: {len(changed)} files")
    manifest["applied"] = sha or "nothing to commit"
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return {"copied": copied, "skipped": skipped, "considered": considered, "commit": sha}


def run_pass(con, post_ids, cfg, report, run_id=None, dry_run=False, api_key=None) -> dict:
    """Run one Claude call per batch and keep finished work on a usage limit."""
    size = max(1, int(cfg["ideas"]["batch_size"]))
    batches = [post_ids[i:i + size] for i in range(0, len(post_ids), size)]
    result = {"created": [], "updated": [], "considered": []}
    folder = dry_run_dir(run_id) if dry_run else ideas_dir()
    if dry_run:
        folder.mkdir(parents=True, exist_ok=True)
        manifest = read_manifest(folder) or {
            "run_id": run_id, "considered": [],
            "base": {p.name: _sha(p) for p in ideas_dir().glob("idea-*.md")}}
    for n, batch in enumerate(batches, start=1):
        report(f"ideas batch {n}/{len(batches)}: {' '.join(batch)}")
        before = brain.snapshot()  # in a dry run too: proves the brain was left alone
        rows = con.execute(f"SELECT id, note_path FROM posts WHERE id IN ({db.placeholders(batch)})", batch)
        paths = {r["id"]: r["note_path"] for r in rows}
        mode = ("This is a dry run. Write every idea you would create or update into the target folder. "
                "For updates, write a full copy under the existing file name. Change nothing in ~/Projects/brain."
                if dry_run else "Write the ideas into the target folder.")
        prompt = notes.render("ideas.md", count=len(batch), notes="\n".join(f"{pid}  {paths.get(pid) or ''}" for pid in batch),
                              today=date.today().isoformat(), ideas_dir=folder, mode=mode,
                              max_new=cfg["ideas"]["max_new_per_pass"])
        limit = None
        try:
            res = claude_cli.run(prompt, schema=REPORT_SCHEMA, cwd=str(ROOT),
                                 add_dirs=[str(brain_dir(cfg))] + ([str(folder)] if dry_run else []),
                                 model=cfg["ideas"]["model"], backend=cfg["notes"]["backend"], api_key=api_key,
                                 on_line=lambda line: report(f"  {line}"))
        except UsageLimit as exc:
            limit, res = exc, getattr(exc, "result", None)
        notes.add_usage(con, run_id, res)
        if res:
            report(f"ideas batch {n} usage: {notes.describe_usage(res)}")
        structured = (res.structured or {}) if res else {}
        batch_counts = {"created": 0, "updated": 0}
        for key in ("created", "updated"):
            for item in structured.get(key, []):
                path = _file_path(item, folder)
                if path is None or not path.is_file():
                    report(f"reported {key} idea is outside {folder} or missing: {item}", level="warn")
                    continue
                result[key].append(str(path))
                batch_counts[key] += 1
                report(f"{key} idea {path.name}")
                meta = notefile.read(path, head_only=True).meta
                for field in ("description", "support", "sources"):
                    if not meta.get(field):
                        report(f"{path.name}: missing {field} front matter", level="warn")
                known = notefile.brain_names()
                for source in _source_names(meta.get("sources")):
                    if source not in known:
                        report(f"{path.name}: source [[{source}]] has no note", level="warn")
        for remark in structured.get("notes", []):
            report(f"  {remark}")
        considered = set(structured.get("considered", [])) & set(batch)
        result["considered"].extend(pid for pid in batch if pid in considered)
        if dry_run:
            manifest["considered"] += [pid for pid in batch if pid in considered]
            (folder / "manifest.json").write_text(json.dumps(manifest, indent=1))
        if dry_run:
            touched = brain.changed_since(before, ("",))
            if touched:  # never committed; Marco decides what to keep
                report(f"brain files changed during the dry run (by the agent, or by you in Obsidian; nothing was committed): {', '.join(touched)}", level="error")
        else:
            if considered:
                con.executemany("UPDATE posts SET ideas_checked_at = ? WHERE id = ?",
                                [(db.now(), pid) for pid in batch if pid in considered])
                con.commit()
            sha, changed = brain.index_and_commit(before, brain.IDEA_PATHS,
                                                   f"agent: ideas pass {n} (run {run_id})")
            notes.add_commit(con, run_id, sha)
            if sha:
                report(f"brain commit {sha}: {len(changed)} files")
        if run_id:
            con.execute("UPDATE runs SET ideas_created = ideas_created + ?, ideas_updated = ideas_updated + ? WHERE id = ?",
                        (batch_counts["created"], batch_counts["updated"], run_id))
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


def list_ideas(folder=None) -> list[dict]:
    out = []
    for path in (folder or ideas_dir()).glob("idea-*.md"):
        note = notefile.read(path, head_only=True)
        meta = note.meta
        sources = _source_names(meta.get("sources"))
        try:
            support = int(meta.get("support", len(sources)))
        except (ValueError, TypeError):
            support = len(sources)
        out.append({"name": path.stem, "path": path, "title": note.title,
                    "description": meta.get("description", ""), "status": meta.get("status", "new"),
                    "support": support, "created": str(meta.get("created", "")),
                    "updated": str(meta.get("updated", "")), "sources": sources,
                    "tags": meta.get("tags", [])})
    return sorted(out, key=lambda x: (x["support"], x["updated"]), reverse=True)
