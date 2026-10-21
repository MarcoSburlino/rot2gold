"""One pipeline run at a time.

The lock is one the operating system keeps on an open file: only one process can hold it, and it is
dropped when that process exits, even after a crash or a kill, so it can never go stale.
Linux and macOS: flock. Windows: msvcrt.locking on one byte far past the text, because Windows
also blocks reading a locked range. The holder writes who it is into the file, so others can say who is running.
"""

import json
import os
from datetime import datetime, timezone

from .config import DATA
from .errors import LockHeld

LOCK_PATH = DATA / "r2g.lock"

if os.name == "nt":
    import msvcrt

    _FAR = 2 ** 30

    def _try_lock(f) -> None:
        f.seek(_FAR)
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise BlockingIOError from None
        finally:
            f.seek(0)

    def _unlock(f) -> None:
        f.seek(_FAR)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        f.seek(0)
else:
    import fcntl

    def _try_lock(f) -> None:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(f) -> None:
        fcntl.flock(f, fcntl.LOCK_UN)


def _open():
    DATA.mkdir(parents=True, exist_ok=True)
    return open(LOCK_PATH, "a+b")


def _read(f) -> dict:
    f.seek(0)
    try:
        return json.loads(f.read().decode() or "{}")
    except (ValueError, UnicodeDecodeError):
        return {}


def holder() -> dict | None:
    """Who holds the lock, or None if nobody does."""
    with _open() as f:
        try:
            _try_lock(f)
        except BlockingIOError:
            return _read(f)
        _unlock(f)
        return None


def describe(info: dict) -> str:
    origin = {"app": "an app run", "terminal": "a terminal run"}.get(info.get("origin"), "another run")
    started = info.get("started", "")[11:16]
    return f"{origin} (pid {info.get('pid', '?')}, started {started} UTC, `{info.get('command', 'r2g')}`)"


class PipelineLock:
    """`with PipelineLock("terminal", "r2g run"):` holds the lock for the block."""

    def __init__(self, origin: str, command: str):
        self.info = {"pid": os.getpid(), "origin": origin, "command": command,
                     "started": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        self.f = None

    def __enter__(self):
        self.f = _open()
        try:
            _try_lock(self.f)
        except BlockingIOError:
            info = _read(self.f)
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
        self.f.write(json.dumps(self.info).encode())
        self.f.flush()

    def __exit__(self, *exc):
        self.f.seek(0)
        self.f.truncate()
        _unlock(self.f)
        self.f.close()
        return False
