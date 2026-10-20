"""Writing to Marco's brain safely: find what a batch changed, index, and commit only that.

Rules from ~/Projects/brain/AGENTS.md: run brain-index and brain-index --check after changes,
stage only the paths you changed (never `git add -A`), commit messages start with "agent: ",
never touch .obsidian/, never push.
"""

import hashlib
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote

from .config import brain_dir
from .errors import BrainError, ToolMissing

# Paths a note-writing batch or an ideas pass (ideas and learnings) may commit (relative to the brain).
NOTE_PATHS = ("Resources/commonplace/",)
IDEA_PATHS = ("Inbox/ideas/", "Inbox/learnings/")
INDEX_FILES = ("index.md", "Resources/resources-index.md", "Inbox/inbox-index.md")


def git(*args, check=True) -> str:
    proc = subprocess.run(["git", "-C", str(brain_dir()), *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise BrainError(f"git {' '.join(args[:2])} failed: {(proc.stderr or proc.stdout).strip()[:300]}")
    return proc.stdout


def _digest(path: Path) -> str | None:
    try:
        return hashlib.sha1(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None  # deleted


def snapshot() -> dict[str, str | None]:
    """Content hash of every file that differs from the last commit (changed, new or deleted)."""
    root = brain_dir()
    out = git("status", "--porcelain", "-z", "--untracked-files=all")
    snap = {}
    entries = out.split("\0")
    i = 0
    while i < len(entries):
        e = entries[i]
        i += 1
        if len(e) < 4:
            continue
        code, path = e[:2], e[3:]
        if code[0] in "RC":  # renames carry the old path in the next entry
            i += 1
        snap[path] = _digest(root / path)
    return snap


def changed_since(before: dict, allowed: tuple[str, ...]) -> list[str]:
    """Paths that changed after `before` was taken and are under one of `allowed` (prefixes or files)."""
    after = snapshot()
    changed = [p for p, h in after.items() if before.get(p, "<clean>") != h]
    return sorted(p for p in changed if p.startswith(allowed) and not p.startswith(".obsidian/"))


def brain_index() -> None:
    exe = shutil.which("brain-index") or str(Path.home() / ".local/bin/brain-index")
    if not Path(exe).exists():
        raise ToolMissing("brain-index not found", "It lives in ~/.local/bin/brain-index.")
    for args in ([exe], [exe, "--check"]):
        proc = subprocess.run(args, capture_output=True, text=True)
        if proc.returncode != 0:
            raise BrainError(f"{' '.join(Path(a).name for a in args)} failed: {(proc.stderr or proc.stdout).strip()[:300]}")


def commit(paths: list[str], message: str) -> str | None:
    """Stage exactly `paths` and commit only them. Returns the commit hash, or None if nothing to commit."""
    if not paths:
        return None
    git("add", "--all", "--", *paths)  # --all within these paths also stages deletions
    if not git("diff", "--cached", "--name-only", "--", *paths).strip():
        return None
    git("commit", "-q", "-m", message, "--", *paths)
    return git("rev-parse", "--short", "HEAD").strip()


def index_and_commit(before: dict, allowed: tuple[str, ...], message: str) -> tuple[str | None, list[str]]:
    """brain-index, check, then commit what changed since `before` under `allowed` plus the indexes."""
    brain_index()
    paths = changed_since(before, allowed + INDEX_FILES)
    return commit(paths, message), paths


def note_file(note_path: str) -> Path:
    return brain_dir() / note_path


def obsidian_uri(path: Path) -> str:
    return "obsidian://open?path=" + quote(str(path), safe="")
