"""vn extract: the whole pipeline for some connections, as one recorded run.

Lock → sync → fetch → process → write notes. Only posts in the selected connections are touched.
Progress goes to run_events, which the app streams live. See docs/app-spec.md → "What Extract does".
"""

import os
import sys
import traceback

from . import db, lock, notes, secrets
from .config import load
from .errors import CookiesNeeded, ListingFailed, UsageLimit, VNError
from .events import Reporter
from .fetch import fetch
from .process import process
from .sync import connections, sync_connection


def extract(conn_ids=None, origin: str = "terminal", max_notes: int | None = None, write: bool = True,
            quiet: bool = False) -> dict:
    """Run the pipeline. Returns the finished `runs` row as a dict."""
    cfg = load()
    with lock.PipelineLock(origin, "vn extract") as held:
        con = db.connect()
        db.mark_interrupted_runs(con, os.getpid())
        conns = connections(con, conn_ids)
        if not conns:
            raise SystemExit("No connections yet. Add one: vn conn add <collection URL>")
        ids = [c["id"] for c in conns]
        cur = con.execute("INSERT INTO runs (origin, connection_ids, backend, model, pid, started_at)"
                          " VALUES (?, ?, ?, ?, ?, ?)",
                          (origin, ",".join(map(str, ids)), cfg["notes"]["backend"], cfg["notes"]["model"],
                           os.getpid(), db.now()))
        con.commit()
        run_id = cur.lastrowid
        held.update(run_id=run_id)
        report = Reporter(run_id, quiet=quiet)
        counts = dict.fromkeys(("posts_listed", "posts_fetched", "posts_processed", "posts_noted", "posts_skipped"), 0)
        status, error = "ok", None

        def save_counts():  # after each stage, so the app shows progress while the run goes on
            con.execute(f"UPDATE runs SET {', '.join(f'{k} = ?' for k in counts)} WHERE id = ?", (*counts.values(), run_id))
            con.commit()

        try:
            report(f"run {run_id}: {', '.join(c['name'] for c in conns)}")
            report.set_stage("sync")
            failed = []
            for conn in conns:  # one broken connection doesn't stop the others
                try:
                    counts["posts_listed"] += sync_connection(con, conn, report)[0]
                except (CookiesNeeded, ListingFailed) as exc:
                    report(str(exc), level="error")
                    failed.append(exc)
            if len(failed) == len(conns):
                raise failed[0]

            save_counts()
            report.set_stage("fetch")
            counts["posts_fetched"] = fetch(None, ids=db.connection_post_ids(con, ids, "new"), report=report)

            save_counts()
            report.set_stage("process")
            counts["posts_processed"] = process(None, ids=db.connection_post_ids(con, ids, "fetched"), report=report)

            save_counts()
            waiting = db.connection_post_ids(con, ids, "processed")
            if write and waiting:
                report.set_stage("notes")
                limit = max_notes or int(cfg["notes"]["max_per_run"])
                todo = waiting[:limit]
                report(f"{len(waiting)} posts waiting for a note; writing {len(todo)} "
                       f"in batches of {cfg['notes']['batch_size']} ({cfg['notes']['backend']}, {cfg['notes']['model']})")
                api_key = secrets.get_api_key() if cfg["notes"]["backend"] == "api" else None
                counts["posts_noted"], counts["posts_skipped"] = notes.write_notes(
                    con, todo, cfg, report, run_id, api_key=api_key)
                left = len(db.connection_post_ids(con, ids, "processed"))
                if left:
                    report(f"{left} posts still wait for a note: run Extract again")
            elif waiting:
                report(f"{len(waiting)} posts wait for a note (note writing was turned off for this run)")
            report.set_stage("done")
        except KeyboardInterrupt:
            status, error = "stopped", "Stopped. Finished work is saved; Extract again to continue."
            report(error, level="warn")
        except UsageLimit as exc:
            status, error = "stopped", str(exc)
            report(error, level="warn")
        except VNError as exc:
            status, error = "failed", str(exc)
            report(error, level="error")
        except Exception as exc:
            status, error = "failed", f"{type(exc).__name__}: {exc}"
            report(traceback.format_exc(limit=6), level="error")
        finally:
            try:
                con.execute(f"UPDATE runs SET status = ?, error = ?, finished_at = ?,"
                            f" {', '.join(f'{k} = ?' for k in counts)} WHERE id = ?",
                            (status, error, db.now(), *counts.values(), run_id))
                con.commit()
            except Exception as exc:  # the app then shows the run as interrupted; say why here
                print(f"could not record the end of run {run_id}: {exc}", file=sys.stderr)
        return dict(con.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone())
