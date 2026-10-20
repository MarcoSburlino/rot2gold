"""Record a locked pipeline run and its events, including interrupted work."""

import os
import sys
import traceback
from contextlib import contextmanager
from dataclasses import dataclass

from . import db, lock
from .errors import UsageLimit, VNError
from .events import Reporter


@dataclass
class Run:
    run_id: int
    report: Reporter
    counts: dict
    con: object

    def save_counts(self):
        self.con.execute(f"UPDATE runs SET {', '.join(f'{k} = ?' for k in self.counts)} WHERE id = ?",
                         (*self.counts.values(), self.run_id))
        self.con.commit()

    def row(self):
        return dict(self.con.execute("SELECT * FROM runs WHERE id = ?", (self.run_id,)).fetchone())


@contextmanager
def recorded_run(origin, command, kind, connection_ids, cfg, quiet=False):
    """Own the lock, row and final status for both Extract and ideas runs."""
    with lock.PipelineLock(origin, command) as held:
        con = db.connect()
        db.mark_interrupted_runs(con, os.getpid())
        model = cfg["ideas"]["model"] if kind.startswith("ideas") else cfg["notes"]["model"]
        cur = con.execute("INSERT INTO runs (origin, kind, connection_ids, backend, model, pid, started_at)"
                          " VALUES (?, ?, ?, ?, ?, ?, ?)",
                          (origin, kind, ",".join(map(str, connection_ids or [])), cfg["notes"]["backend"],
                           model, os.getpid(), db.now()))
        con.commit()
        run_id = cur.lastrowid
        held.update(run_id=run_id)
        run = Run(run_id, Reporter(run_id, quiet=quiet),
                  dict.fromkeys(("posts_listed", "posts_fetched", "posts_processed", "posts_noted",
                                 "posts_skipped", "ideas_created", "ideas_updated",
                                 "learnings_created", "learnings_updated"), 0), con)
        status, error = "ok", None
        try:
            yield run
        except KeyboardInterrupt:
            status, error = "stopped", "Stopped. Finished work is saved; Extract again to continue."
            run.report(error, level="warn")
        except UsageLimit as exc:
            status, error = "stopped", str(exc)
            run.report(error, level="warn")
        except VNError as exc:
            status, error = "failed", str(exc)
            run.report(error, level="error")
        except Exception as exc:
            status, error = "failed", f"{type(exc).__name__}: {exc}"
            run.report(traceback.format_exc(limit=6), level="error")
        finally:
            try:
                saved = run.row()
                for key in ("ideas_created", "ideas_updated", "learnings_created", "learnings_updated"):
                    run.counts[key] = max(run.counts[key], saved[key])
                run.con.execute(f"UPDATE runs SET status = ?, error = ?, finished_at = ?,"
                                f" {', '.join(f'{k} = ?' for k in run.counts)} WHERE id = ?",
                                (status, error, db.now(), *run.counts.values(), run_id))
                run.con.commit()
            except Exception as exc:
                print(f"could not record the end of run {run_id}: {exc}", file=sys.stderr)
