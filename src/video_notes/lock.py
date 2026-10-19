"""One pipeline run at a time.

flock is a lock the kernel keeps on an open file: only one process can hold it, and the kernel
drops it when that process exits, even after a crash or kill -9, so it can never go stale.
The holder writes who it is into the file, so others can say who is running.
"""

import fcntl
import json
import os
from datetime import datetime, timezone

from .config import DATA
from .errors import LockHeld

LOCK_PATH = DATA / "vn.lock"


def _open():
    DATA.mkdir(parents=True, exist_ok=True)
    return open(LOCK_PATH, "a+")


def holder() -> dict | None:
    """Who holds the lock, or None if nobody does."""
    with _open() as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            f.seek(0)
            try:
                return json.loads(f.read() or "{}")
            except json.JSONDecodeError:
                return {}
        fcntl.flock(f, fcntl.LOCK_UN)
        return None


def describe(info: dict) -> str:
    origin = {"app": "an app run", "terminal": "a terminal run"}.get(info.get("origin"), "another run")
    started = info.get("started", "")[11:16]
    return f"{origin} (pid {info.get('pid', '?')}, started {started} UTC, `{info.get('command', 'vn')}`)"


class PipelineLock:
    """`with PipelineLock("terminal", "vn run"):` holds the lock for the block."""

    def __init__(self, origin: str, command: str):
        self.info = {"pid": os.getpid(), "origin": origin, "command": command,
                     "started": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        self.f = None

    def __enter__(self):
        self.f = _open()
        try:
            fcntl.flock(self.f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.f.seek(0)
            try:
                info = json.loads(self.f.read() or "{}")
            except json.JSONDecodeError:
                info = {}
            self.f.close()
            raise LockHeld(f"The pipeline is already running: {describe(info)}.") from None
        self._write()
        return self

    def update(self, **fields) -> None:
        self.info |= fields
        self._write()

    def _write(self) -> None:
        self.f.seek(0)
        self.f.truncate()
        json.dump(self.info, self.f)
        self.f.flush()

    def __exit__(self, *exc):
        self.f.seek(0)
        self.f.truncate()
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()
        return False
