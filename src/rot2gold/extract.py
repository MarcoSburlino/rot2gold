"""r2g extract: sync, fetch, process, notes and ideas for selected connections."""

from . import ai, db, ideas, notes, vault
from .config import is_set_up, load
from .errors import CookiesNeeded, ListingFailed
from .fetch import fetch
from .process import process
from .runs import recorded_run
from .sync import connections, sync_connection


def extract(conn_ids=None, origin: str = "terminal", max_notes: int | None = None, write: bool = True,
            quiet: bool = False, find_ideas: bool = True) -> dict:
    """Run the pipeline. Returns the finished `runs` row as a dict."""
    cfg = load()
    if not is_set_up(cfg):
        raise SystemExit("Rot2Gold isn't set up yet: run `r2g` (or `r2g setup`) first.")
    conns = connections(db.connect(), conn_ids)
    if not conns:
        raise SystemExit("No connections yet. Add one: r2g conn add <collection URL>")
    ids = [c["id"] for c in conns]
    with recorded_run(origin, "r2g extract", "extract", ids, cfg, quiet) as run:
        con, report, counts, run_id = run.con, run.report, run.counts, run.run_id
        report(f"run {run_id}: {', '.join(c['name'] for c in conns)}")
        vault.prepare_and_report(cfg, report)
        report.set_stage("sync")
        failed = []
        for conn in conns:
            try:
                counts["posts_listed"] += sync_connection(con, conn, report)[0]
            except (CookiesNeeded, ListingFailed) as exc:
                report(str(exc), level="error")
                failed.append(exc)
        if len(failed) == len(conns):
            raise failed[0]
        run.save_counts()
        report.set_stage("fetch")
        counts["posts_fetched"] = fetch(None, ids=db.connection_post_ids(con, ids, "new"), report=report)
        run.save_counts()
        report.set_stage("process")
        counts["posts_processed"] = process(None, ids=db.connection_post_ids(con, ids, "fetched"), report=report)
        run.save_counts()
        waiting = db.connection_post_ids(con, ids, "processed")
        if write and waiting:
            report.set_stage("notes")
            limit = max_notes or int(cfg["notes"]["max_per_run"])
            todo = waiting[:limit]
            report(f"{len(waiting)} posts waiting for a note; writing {len(todo)} "
                   f"in batches of {cfg['notes']['batch_size']} ({ai.PROVIDERS[ai.provider(cfg)]}, {cfg['notes']['model'] or 'default model'})")
            api_key = ai.api_key(cfg)
            counts["posts_noted"], counts["posts_skipped"] = notes.write_notes(
                con, todo, cfg, report, run_id, api_key=api_key)
            left = len(db.connection_post_ids(con, ids, "processed"))
            if left:
                report(f"{left} posts still wait for a note: run Extract again")
        elif waiting:
            report(f"{len(waiting)} posts wait for a note (note writing was turned off for this run)")
        run.save_counts()
        if write and find_ideas:
            todo = ideas.candidates_new(con, ids, cfg=cfg)
            if todo:
                report.set_stage("ideas")
                report(f"{len(todo)} notes waiting to be checked for ideas, learnings and events")
                api_key = ai.api_key(cfg)
                found = ideas.run_pass(con, todo, cfg, report, run_id, api_key=api_key)
                counts.update(ideas.counts(found))
        report.set_stage("done")
    return run.row()
