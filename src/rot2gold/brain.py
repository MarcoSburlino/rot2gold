"""Writing to the vault safely: find what a batch changed, run the after-write commands, and commit only that.

Rules: stage only the paths the app changed (never `git add -A`), commit messages start with "agent: ",
never touch .obsidian/, never push. Without Git, changes are found by hashing the files the app writes,
and nothing is committed.
"""

import hashlib
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote

from .config import brain_dir, load, vault_rel
from .errors import BrainError, ToolMissing


def note_paths(cfg: dict | None = None) -> tuple[str, ...]:
    """What a note-writing batch may change: the video notes, the hub and the quotes note."""
    return (vault_rel("videos", cfg) + "/", vault_rel("hub", cfg), vault_rel("quotes", cfg))


def idea_paths(cfg: dict | None = None) -> tuple[str, ...]:
    """What an ideas pass may change: the idea, learning and event folders."""
    return tuple(vault_rel(key, cfg) + "/" for key in ("ideas", "learnings", "events"))


def extra_paths(cfg: dict | None = None) -> tuple[str, ...]:
    """Files the after-write commands change that are committed too (e.g. an index)."""
    return tuple(str(p) for p in (cfg or load())["vault"]["commit_also"])


def uses_git(cfg: dict | None = None) -> bool:
    mode = (cfg or load())["vault"]["git"]
    return mode == "on" or (mode == "auto" and (brain_dir(cfg) / ".git").exists())


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
    """With Git: the content hash of every file that differs from the last commit (changed, new or deleted).
    Without Git: the hash of every file the app may write."""
    root = brain_dir()
    if not uses_git():
        snap = {}
        for rel in note_paths() + idea_paths() + extra_paths():
            path = root / rel
            for file in ([path] if path.is_file() else path.rglob("*") if path.is_dir() else []):
                if file.is_file():
                    snap[file.relative_to(root).as_posix()] = _digest(file)
        return snap
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
    if uses_git():
        changed = [p for p, h in after.items() if before.get(p, "<clean>") != h]
    else:
        changed = [p for p in before.keys() | after.keys() if before.get(p) != after.get(p)]
    return sorted(p for p in changed if p.startswith(allowed) and not p.startswith(".obsidian/"))


def run_after_write(cfg: dict | None = None) -> None:
    """The user's after-write commands ([vault] after_write), run in the vault, in order."""
    for cmd in (cfg or load())["vault"]["after_write"]:
        local = Path.home() / ".local/bin" / cmd[0]
        exe = shutil.which(cmd[0]) or (str(local) if local.exists() else None)
        if not exe:
            raise ToolMissing(f"{cmd[0]} not found", "It is listed in [vault] after_write in your config.toml.")
        proc = subprocess.run([exe, *cmd[1:]], cwd=brain_dir(cfg), capture_output=True, text=True)
        if proc.returncode != 0:
            raise BrainError(f"{' '.join(cmd)} failed: {(proc.stderr or proc.stdout).strip()[:300]}")


def commit(paths: list[str], message: str) -> str | None:
    """Stage exactly `paths` and commit only them. Returns the commit hash, or None if nothing to commit."""
    if not paths or not uses_git():
        return None
    git("add", "--all", "--", *paths)  # --all within these paths also stages deletions
    if not git("diff", "--cached", "--name-only", "--", *paths).strip():
        return None
    git("commit", "-q", "-m", message, "--", *paths)
    return git("rev-parse", "--short", "HEAD").strip()


def finish(before: dict, allowed: tuple[str, ...], message: str) -> tuple[str | None, list[str]]:
    """Run the after-write commands, then commit what changed since `before` under `allowed`
    (plus the files those commands change). Returns (commit hash or None, changed paths)."""
    run_after_write()
    paths = changed_since(before, allowed + extra_paths())
    return commit(paths, message), paths


def note_file(note_path: str) -> Path:
    return brain_dir() / note_path


def obsidian_uri(path: Path) -> str:
    return "obsidian://open?path=" + quote(str(path), safe="")
