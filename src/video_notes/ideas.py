"""Find ideas (things to do) and learnings (things understood) across finished notes, and commit each batch.

One pass looks for both kinds, so the same Claude call can link a learning to the ideas that apply it.
Each kind has its own folder and file prefix: Inbox/ideas/idea-*.md and Inbox/learnings/learning-*.md.
"""

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


KINDS = {"idea": "Inbox/ideas", "learning": "Inbox/learnings"}


def kind_dir(kind: str) -> Path:
    return brain_dir() / KINDS[kind]


def ideas_dir() -> Path:
    return kind_dir("idea")


def kind_of(name: str) -> str | None:
    """'idea-try-x' → 'idea', 'learning-y.md' → 'learning', anything else → None."""
    prefix = Path(name).name.split("-", 1)[0]
    return prefix if prefix in KINDS and "-" in Path(name).name else None


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
    """Notes new since `[ideas] since` not yet checked for ideas, then notes of any age not yet
    checked for learnings: so Extract also works through older notes for learnings, batch by batch."""
    since = (cfg or load())["ideas"]["since"]
    sql = ("SELECT p.id FROM posts p WHERE p.status = 'done' AND p.note_path IS NOT NULL"
           " AND ((p.ideas_checked_at IS NULL AND substr(p.updated_at, 1, 10) >= ?) OR p.learnings_checked_at IS NULL)")
    args = [since]
    if conn_ids is not None:
        if not conn_ids:
            return []
        sql += (f" AND EXISTS (SELECT 1 FROM connection_posts cp WHERE cp.post_id = p.id"
                f" AND cp.connection_id IN ({db.placeholders(conn_ids)}))")
        args.extend(conn_ids)
    # New notes (due for ideas) first, then the older ones waiting only for learnings.
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
                                           " AND (ideas_checked_at IS NULL OR learnings_checked_at IS NULL) ORDER BY rowid")
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


def note_files(folder: Path) -> list[Path]:
    """Idea and learning files directly inside `folder` (a dry run keeps both kinds side by side)."""
    return sorted(p for kind in KINDS for p in folder.glob(f"{kind}-*.md"))


def _checks(con, ids) -> dict[str, dict]:
    """Which checks each post still needs: {'ideas': bool, 'learnings': bool}."""
    rows = con.execute(f"SELECT id, ideas_checked_at, learnings_checked_at FROM posts WHERE id IN ({db.placeholders(ids)})",
                       list(ids)) if ids else []
    return {r["id"]: {"ideas": r["ideas_checked_at"] is None, "learnings": r["learnings_checked_at"] is None} for r in rows}


def _mark(con, ideas_ids, learning_ids) -> None:
    stamp = db.now()
    con.executemany("UPDATE posts SET ideas_checked_at = ? WHERE id = ? AND ideas_checked_at IS NULL",
                    [(stamp, pid) for pid in ideas_ids])
    con.executemany("UPDATE posts SET learnings_checked_at = ? WHERE id = ? AND learnings_checked_at IS NULL",
                    [(stamp, pid) for pid in learning_ids])
    con.commit()


def apply_dry_run(con, run_id: int, report, apply_run_id: int | None = None) -> dict:
    """Copy a reviewed dry run into the brain and mark its notes checked, without calling Claude again.

    An idea or learning Marco changed (or deleted) after the dry run is skipped, so his edits are never overwritten.
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
    counts = dict.fromkeys(("ideas_created", "ideas_updated", "learnings_created", "learnings_updated"), 0)
    for src in note_files(folder):
        target = kind_dir(kind_of(src.name))
        target.mkdir(parents=True, exist_ok=True)
        dst = target / src.name
        current = _sha(dst) if dst.is_file() else None
        if current != base.get(src.name):
            skipped.append(src.name)
            report(f"skipped {src.name}: changed in the brain after the dry run", level="warn")
            continue
        shutil.copyfile(src, dst)
        copied.append(src.name)
        counts[f"{kind_of(src.name)}s_{'updated' if current else 'created'}"] += 1
        report(f"{'updated' if current else 'created'} {kind_of(src.name)} {src.name}")
    # Dry runs from before learnings existed list only "considered" (checked for ideas).
    needs = _checks(con, set(manifest.get("considered", [])) | set(manifest.get("learned", [])))
    considered = [pid for pid in manifest.get("considered", []) if needs.get(pid, {}).get("ideas")]
    learned = [pid for pid in manifest.get("learned", []) if needs.get(pid, {}).get("learnings")]
    _mark(con, considered, learned)
    sha, changed = brain.index_and_commit(before, brain.IDEA_PATHS, f"agent: ideas and learnings from dry run {run_id}")
    if sha:
        report(f"brain commit {sha}: {len(changed)} files")
    notes.add_commit(con, apply_run_id, sha)
    db.add_batch(con, apply_run_id, "apply", 1, post_ids=[str(run_id)], considered=considered, learned=learned)
    manifest["applied"] = sha or "nothing to commit"
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return {"copied": copied, "skipped": skipped, "counts": counts, "considered": considered, "learned": learned, "commit": sha}


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
    result = {"created": [], "updated": [], "learnings_created": [], "learnings_updated": [], "considered": []}
    folder = dry_run_dir(run_id) if dry_run else None
    if dry_run:
        folder.mkdir(parents=True, exist_ok=True)
        manifest = read_manifest(folder) or {
            "run_id": run_id, "considered": [], "learned": [],
            "base": {p.name: _sha(p) for kind in KINDS for p in kind_dir(kind).glob(f"{kind}-*.md")}}
        manifest.setdefault("learned", [])
    else:
        kind_dir("learning").mkdir(parents=True, exist_ok=True)
    for n, batch in enumerate(batches, start=1):
        report(f"ideas batch {n}/{len(batches)}: {' '.join(batch)}")
        before = brain.snapshot()  # in a dry run too: proves the brain was left alone
        rows = con.execute(f"SELECT id, note_path FROM posts WHERE id IN ({db.placeholders(batch)})", batch)
        paths = {r["id"]: r["note_path"] for r in rows}
        needs = _checks(con, batch)
        look_for = {pid: " and ".join(k for k in ("ideas", "learnings") if needs.get(pid, {}).get(k)) or "learnings"
                    for pid in batch}
        mode = ("This is a dry run. Write every idea and learning you would create or update into "
                f"{folder}. For updates, write a full copy under the existing file name. Change nothing in ~/Projects/brain."
                if dry_run else f"Write ideas into {ideas_dir()} and learnings into {kind_dir('learning')}.")
        # Re-read every batch: the previous batch may have created or updated some.
        known_ideas, known_learnings = _known("idea", folder), _known("learning", folder)
        prompt = notes.render("ideas.md", count=len(batch),
                              notes="\n".join(f"{pid}  {paths.get(pid) or ''}  [{look_for[pid]}]" for pid in batch),
                              today=date.today().isoformat(), ideas_dir=folder or ideas_dir(),
                              learnings_dir=folder or kind_dir("learning"), mode=mode,
                              max_new=cfg["ideas"]["max_new_per_pass"],
                              max_new_learnings=cfg["ideas"].get("max_new_learnings_per_pass", 8),
                              existing_count=len(known_ideas), existing=catalog(known_ideas),
                              existing_learnings_count=len(known_learnings), existing_learnings=catalog(known_learnings))
        limit = None
        try:
            res = claude_cli.run(prompt, schema=REPORT_SCHEMA, cwd=str(ROOT),
                                 add_dirs=[str(brain_dir(cfg))] + ([str(folder)] if dry_run else []),
                                 model=cfg["ideas"]["model"], backend=cfg["notes"]["backend"], api_key=api_key,
                                 max_budget_usd=cfg["notes"].get("max_budget_usd_per_batch"),
                                 on_line=lambda line: report(f"  {line}"))
        except UsageLimit as exc:
            limit, res = exc, getattr(exc, "result", None)
        notes.add_usage(con, run_id, res)
        if res:
            report(f"ideas batch {n} usage: {notes.describe_usage(res)}")
        structured = (res.structured or {}) if res else {}
        batch_counts = dict.fromkeys(("ideas_created", "ideas_updated", "learnings_created", "learnings_updated"), 0)
        names = notefile.brain_names()
        for key in ("created", "updated"):
            for item in structured.get(key, []):
                kind = kind_of(item)
                path = _file_path(item, folder or kind_dir(kind)) if kind else None
                if path is None:
                    report(f"reported {key} file is not an idea or learning in its folder, or is missing: {item}", level="warn")
                    continue
                result[key if kind == "idea" else f"learnings_{key}"].append(str(path))
                batch_counts[f"{kind}s_{key}"] += 1
                report(f"{key} {kind} {path.name}")
                meta = notefile.read(path, head_only=True).meta
                for field in ("description", "support", "sources"):
                    if not meta.get(field):
                        report(f"{path.name}: missing {field} front matter", level="warn")
                for source in _source_names(meta.get("sources")):
                    if source not in names:
                        report(f"{path.name}: source [[{source}]] has no note", level="warn")
        for remark in structured.get("notes", []):
            report(f"  {remark}")
        considered = set(structured.get("considered", [])) & set(batch)
        result["considered"].extend(pid for pid in batch if pid in considered)
        checked_ideas = [pid for pid in batch if pid in considered and needs.get(pid, {}).get("ideas")]
        checked_learnings = [pid for pid in batch if pid in considered and needs.get(pid, {}).get("learnings")]
        if dry_run:
            manifest["considered"] += checked_ideas
            manifest["learned"] += checked_learnings
            (folder / "manifest.json").write_text(json.dumps(manifest, indent=1))
            touched = brain.changed_since(before, ("",))
            if touched:  # never committed; Marco decides what to keep
                report(f"brain files changed during the dry run (by the agent, or by you in Obsidian; nothing was committed): {', '.join(touched)}", level="error")
        else:
            _mark(con, checked_ideas, checked_learnings)
            sha, changed = brain.index_and_commit(before, brain.IDEA_PATHS,
                                                   f"agent: ideas pass {n} (run {run_id})")
            notes.add_commit(con, run_id, sha)
            if sha:
                report(f"brain commit {sha}: {len(changed)} files")
        db.add_batch(con, run_id, "ideas", n, batch, considered=() if dry_run else checked_ideas,
                     learned=() if dry_run else checked_learnings, res=res, error=limit)
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
    """One line per existing idea or learning, for the prompt: enough to compare a candidate with all of them."""
    if not items:
        return "(none yet)"
    return "\n".join(f"- {i['name']}.md · {i['title']} · {i['description'] or '—'} · {i['status']} · "
                     + (", ".join(i["sources"]) or "no sources") for i in sorted(items, key=lambda i: i["name"]))


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
        out.append({"name": path.stem, "kind": kind, "path": path, "title": note.title,
                    "description": meta.get("description", ""), "status": meta.get("status", "new"),
                    "support": support, "created": str(meta.get("created", "")),
                    "updated": str(meta.get("updated", "")), "sources": sources,
                    "tags": meta.get("tags", [])})
    return sorted(out, key=lambda x: (x["support"], x["updated"]), reverse=True)


def list_ideas(folder=None) -> list[dict]:
    return list_items("idea", folder)


def list_learnings(folder=None) -> list[dict]:
    return list_items("learning", folder)
