"""Revert a run's brain commits and reopen only the work those commits completed."""

import json

from . import brain, db, ideas
from .errors import BrainError


def _commits(con, run_id):
    row = con.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not row:
        raise ValueError(f"Run {run_id} does not exist.")
    if row["status"] == "running":
        raise ValueError("This run is still running.")
    if row["undone_at"]:
        raise ValueError("This run was already undone.")
    commits = (row["brain_commits"] or "").split()
    if not commits:
        raise ValueError("This run has no brain commits to undo.")
    return commits


def undo_run(con, run_id: int, report) -> dict:
    commits = _commits(con, run_id)
    if brain.git("diff", "--cached", "--name-only").strip():
        raise ValueError("The brain has staged changes. Commit or unstage them before undoing this run.")
    touched, added = set(), set()
    for sha in commits:
        for line in brain.git("show", "--format=", "--name-status", sha).splitlines():
            parts = line.split("\t")
            if len(parts) > 1:
                touched.update(parts[1:])
                if parts[0] == "A":
                    added.add(parts[1])
    dirty = set(brain.git("status", "--porcelain", "-z", "--untracked-files=all").split("\0"))
    dirty_paths = {item[3:] for item in dirty if len(item) > 3}
    conflict = sorted((touched | set(brain.INDEX_FILES)) & dirty_paths)
    if conflict:
        raise ValueError("Files from this run have uncommitted changes: " + ", ".join(conflict))
    for sha in reversed(commits):
        try:
            brain.git("revert", "--no-commit", sha)
        except BrainError as exc:
            brain.git("revert", "--abort", check=False)
            raise BrainError("Later changes touched the same files, so this run can't be undone automatically: "
                             + str(exc)) from None
    before = brain.snapshot()
    brain.brain_index()
    indexes = brain.changed_since(before, brain.INDEX_FILES)
    if indexes:
        brain.git("add", "--all", "--", *indexes)
    brain.git("commit", "-m", f"agent: undo run {run_id}")
    undo_sha = brain.git("rev-parse", "--short", "HEAD").strip()
    rows = con.execute("SELECT * FROM batches WHERE run_id = ? ORDER BY id", (run_id,)).fetchall()
    noted = {pid for row in rows for pid in (row["noted"] or "").split()}
    considered = {pid for row in rows for pid in (row["considered"] or "").split()}
    if not rows:
        noted = {row["id"] for row in con.execute("SELECT id, note_path FROM posts WHERE note_path IS NOT NULL")
                 if row["note_path"] in added}
        report("This run predates batch records; noted posts were found from files added by its commits.")
    reopened = []
    for pid in sorted(noted):
        row = con.execute("SELECT note_path FROM posts WHERE id = ?", (pid,)).fetchone()
        if row and row["note_path"] and not brain.note_file(row["note_path"]).exists():
            con.execute("UPDATE posts SET status = 'processed', note_path = NULL, updated_at = ? WHERE id = ?",
                        (db.now(), pid))
            reopened.append(pid)
    for pid in considered:
        con.execute("UPDATE posts SET ideas_checked_at = NULL WHERE id = ?", (pid,))
    restored = []
    for row in rows:
        if row["kind"] == "delete":  # videos deleted with an idea: noted again once their notes are back
            for pid in (row["post_ids"] or "").split():
                post = con.execute("SELECT note_path FROM posts WHERE id = ?", (pid,)).fetchone()
                if post and post["note_path"] and brain.note_file(post["note_path"]).exists():
                    con.execute("UPDATE posts SET status = 'done', skip_reason = NULL, updated_at = ? WHERE id = ?",
                                (db.now(), pid))
                    restored.append(pid)
        if row["kind"] == "apply":
            for dry_id in (row["post_ids"] or "").split():
                folder = ideas.dry_run_dir(dry_id)
                manifest = ideas.read_manifest(folder)
                if manifest:
                    manifest.pop("applied", None)
                    (folder / "manifest.json").write_text(json.dumps(manifest, indent=1))
    con.execute("UPDATE runs SET undone_at = ? WHERE id = ?", (db.now(), run_id))
    con.commit()
    report(f"Undo commit {undo_sha}; {len(reopened)} posts returned to the queue; {len(considered)} ideas checks cleared"
           + (f"; {len(restored)} deleted videos restored" if restored else ""))
    return {"commit": undo_sha, "reopened": reopened, "considered": sorted(considered), "restored": restored}
