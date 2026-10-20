"""Delete an idea, learning or event Marco no longer wants, and optionally the video notes behind it.

Deleting is a recorded run with its own brain commit, so History lists it and Undo brings the
files back. A deleted video's post stays in the database as skipped, so the next Extract
doesn't download and write it again.
"""

import re
from pathlib import Path

from . import brain, db, ideas, notefile, notes

SKIP_REASON = "deleted by you with the {kind} “{title}”"


def plan(con, name: str) -> dict:
    """What deleting `name` would remove: the item, and which of its videos could go with it.

    A video that also supports another idea, learning or event is kept, so nothing else loses a source.
    """
    kind = ideas.kind_of(name)
    if not kind or Path(name).name != name or not (ideas.kind_dir(kind) / f"{name}.md").is_file():
        raise ValueError(f"No idea, learning or event named {name}. It may have been renamed or moved in Obsidian.")
    everything = [item for k in ideas.KINDS for item in ideas.list_items(k)]
    idea = next(i for i in everything if i["name"] == name)
    used_elsewhere = {}
    for other in everything:
        if other["name"] != name:
            for source in other["sources"]:
                used_elsewhere.setdefault(source, other["title"])
    posts = {Path(r["note_path"]).stem: dict(r) for r in con.execute(
        "SELECT id, note_path FROM posts WHERE status = 'done' AND note_path IS NOT NULL")}
    videos, kept = [], []
    for source in idea["sources"]:
        post = posts.get(source)
        if not post or not brain.note_file(post["note_path"]).is_file():
            continue  # not a video note, or already gone
        title = notefile.read(brain.note_file(post["note_path"]), head_only=True).title
        item = {"name": source, "post_id": post["id"], "note_path": post["note_path"], "title": title}
        if source in used_elsewhere:
            kept.append(item | {"other_idea": used_elsewhere[source]})
        else:
            videos.append(item)
    return {"idea": idea, "videos": videos, "kept": kept}


def _drop_list_lines(path: Path, names: set[str]) -> bool:
    """Remove list items that start with a link to one of `names` (e.g. in commonplace.md)."""
    if not path.is_file() or not names:
        return False
    pattern = re.compile(r"^\s*- \[\[(" + "|".join(map(re.escape, names)) + r")(\|[^\]]*)?\]\]")
    lines = path.read_text().splitlines(keepends=True)
    kept = [line for line in lines if not pattern.match(line)]
    if len(kept) == len(lines):
        return False
    path.write_text("".join(kept))
    return True


def delete_idea(con, name: str, with_videos: bool, report, run_id: int) -> dict:
    """Delete the idea, learning or event file (and its videos' notes), clean the lists that link to them, and commit."""
    found = plan(con, name)
    idea, videos = found["idea"], found["videos"] if with_videos else []
    before = brain.snapshot()

    idea["path"].unlink()
    report(f"deleted {idea['kind']} {idea['path'].name}")
    # List entries pointing at it: Related ideas, Learnings behind it, Use it, Related learnings, Events, Related events.
    for other in (p for kind in ideas.KINDS for p in ideas.kind_dir(kind).glob(f"{kind}-*.md")):
        if _drop_list_lines(other, {name}):
            report(f"removed the link to it from {other.name}")

    for video in videos:
        brain.note_file(video["note_path"]).unlink()
        con.execute("UPDATE posts SET status = 'skipped', skip_reason = ?, updated_at = ? WHERE id = ?",
                    (SKIP_REASON.format(kind=idea["kind"], title=idea["title"]), db.now(), video["post_id"]))
        report(f"deleted video note {video['note_path']}")
    con.commit()
    if videos and _drop_list_lines(brain.brain_dir() / "Resources/commonplace/commonplace.md", {v["name"] for v in videos}):
        report("removed the deleted videos from commonplace.md")
    for video in found["kept"] if with_videos else []:
        report(f"kept {video['name']}: it also supports “{video['other_idea']}”")

    message = f"agent: delete {name}" + (f" and {len(videos)} video notes" if videos else "")
    sha, changed = brain.index_and_commit(before, brain.IDEA_PATHS + brain.NOTE_PATHS, message)
    if sha:
        report(f"brain commit {sha}: {len(changed)} files")
    notes.add_commit(con, run_id, sha)
    # Undo reads this batch to put the videos back to "noted" once their notes are restored.
    db.add_batch(con, run_id, "delete", 1, post_ids=[v["post_id"] for v in videos])
    return {"commit": sha, "videos": videos, "kept": found["kept"] if with_videos else []}
