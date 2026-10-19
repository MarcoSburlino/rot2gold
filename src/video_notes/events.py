"""Progress reporting. Stages call report("message", post_id=..., level=...).

`echo` only prints (plain `vn` commands). A run's Reporter also stores every line in run_events,
which the app streams to the browser.
"""

import sqlite3
import sys

from . import db


def echo(message: str, *, post_id: str | None = None, level: str = "info") -> None:
    print(message, file=sys.stderr if level == "error" else sys.stdout, flush=True)


class Reporter:
    def __init__(self, run_id: int, quiet: bool = False):
        self.run_id, self.quiet, self.stage = run_id, quiet, None
        self.con = db.connect()  # its own connection: a log line waits at most 2 s, never 30
        self.con.execute("PRAGMA busy_timeout = 2000")

    def set_stage(self, stage: str) -> None:
        self.stage = stage
        self._write("UPDATE runs SET stage = ? WHERE id = ?", (stage, self.run_id))
        self(f"── {stage}")

    def _write(self, sql: str, args) -> bool:
        try:
            self.con.execute(sql, args)
            self.con.commit()
            return True
        except sqlite3.OperationalError as exc:
            # A log line must never stop a run. If another connection is mid-write, keep the line on stdout
            # (the app saves stdout in data/logs/) and carry on.
            self.con.rollback()
            echo(f"(run log not saved: {exc})", level="error")
            return False

    def __call__(self, message: str, *, post_id: str | None = None, level: str = "info") -> None:
        if not self.quiet:
            echo(message, level=level)
        saved = self._write("INSERT INTO run_events (run_id, ts, level, stage, post_id, message) VALUES (?, ?, ?, ?, ?, ?)",
                            (self.run_id, db.now(), level, self.stage, post_id, message))
        if not saved and self.quiet:
            echo(message, level=level)
