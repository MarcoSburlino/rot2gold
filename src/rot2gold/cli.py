"""r2g: saved posts → notes in an Obsidian vault. See docs/spec.md (pipeline) and docs/app-spec.md (app)."""

import argparse
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

from . import ai, brain, connections, db, downloaders, ideas, launcher, lock, undo, vault
from .config import load
from .postdata import post_record, post_text
from .errors import VNError


def cmd_pending(args) -> None:
    con = db.connect()
    rows = con.execute("SELECT * FROM posts WHERE status = 'processed' ORDER BY rowid LIMIT ?",
                       (args.n or -1,)).fetchall()
    if args.id:
        rows = con.execute("SELECT * FROM posts WHERE id = ?", (args.id,)).fetchall()
    records = [post_record(con, r) for r in rows]
    if args.json:
        json.dump(records, sys.stdout, ensure_ascii=False, indent=1)
        print()
        return
    if args.ids:
        print("\n".join(r["id"] for r in records))
        return
    for r in records:
        print(post_text(r))
    total = con.execute("SELECT COUNT(*) FROM posts WHERE status = 'processed'").fetchone()[0]
    print(f"({len(records)} shown, {total} pending)")


def cmd_done(args) -> None:
    con = db.connect()
    row = con.execute("SELECT status FROM posts WHERE id = ?", (args.id,)).fetchone()
    if not row:
        raise SystemExit(f"unknown post {args.id}")
    if not brain.note_file(args.note_path).is_file():
        raise SystemExit(f"note not found: {brain.note_file(args.note_path)} (write the note first; the path is relative to the vault)")
    db.set_status(con, args.id, "done", note_path=args.note_path, skip_reason=None)
    print(f"done {args.id} → {args.note_path}")


def cmd_skip(args) -> None:
    con = db.connect()
    if not con.execute("SELECT 1 FROM posts WHERE id = ?", (args.id,)).fetchone():
        raise SystemExit(f"unknown post {args.id}")
    db.set_status(con, args.id, "skipped", skip_reason=args.reason)
    print(f"skipped {args.id}: {args.reason}")


def cmd_status(args) -> None:
    con = db.connect()
    total = con.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    print(f"posts: {total}")
    for r in con.execute("SELECT status, COUNT(*) n FROM posts GROUP BY status ORDER BY status"):
        print(f"  {r['status']:<10} {r['n']}")
    for r in con.execute("SELECT type, COUNT(*) n FROM posts GROUP BY type"):
        print(f"  type {r['type']}: {r['n']}")
    reasons = con.execute("SELECT skip_reason, COUNT(*) n FROM posts WHERE status = 'skipped'"
                          " GROUP BY skip_reason ORDER BY n DESC").fetchall()
    if reasons:
        print("skipped by reason:")
        for r in reasons:
            print(f"  {r['n']:>3}  {r['skip_reason']}")
    for c in connections.all_with_counts(con):
        print(f"connection {c['id']} {c['name']!r}: {c['counts']['total']} posts,"
              f" last sync {(c['last_synced_at'] or 'never')[:16]} ({c['last_sync_source'] or '-'})"
              + (f", last error: {c['last_error']}" if c["last_error"] else ""))
    if info := lock.holder():
        print(f"running: {lock.describe(info)}")


def cmd_conn(args) -> None:
    con = db.connect()
    try:
        if args.action == "list":
            rows = connections.all_with_counts(con)
            if not rows:
                print("No connections yet. Add one: r2g conn add <collection URL>")
            for c in rows:
                n = c["counts"]
                print(f"{c['id']:>3}  {c['name']}  [{c['platform']}, cookies {c['cookies_mode']} from {c['cookie_browser']}]\n     {c['url']}\n     "
                      + ", ".join(f"{connections.LABELS[s]} {n[s]}" for s in connections.STATUSES))
        elif args.action == "add":
            cid = connections.add(con, args.platform, args.url, args.name or "", args.cookies, args.browser)
            print(f"added connection {cid}: {connections.get(con, cid)['name']}")
        elif args.action == "edit":
            connections.update(con, args.id, name=args.name, url=args.url, cookies_mode=args.cookies,
                               browser=args.browser, profile=args.profile)
            print(f"updated connection {args.id}")
        elif args.action == "rm":
            c = connections.get(con, args.id)
            alone = connections.only_here(con, args.id)
            if not args.yes:
                answer = input(f"Delete connection {c['name']!r}? {alone} posts belong only to it; their notes"
                               " and media stay. [y/N] ")
                if answer.strip().lower() != "y":
                    raise SystemExit("not deleted")
            connections.delete(con, args.id)
            print(f"deleted connection {args.id}")
        elif args.action == "links":
            n = connections.set_links(con, args.id, sys.stdin.read())
            print(f"connection {args.id}: {n} post URLs saved (used when listing fails)")
    except ValueError as exc:
        raise SystemExit(str(exc)) from None


def cmd_runs(args) -> None:
    con = db.connect()
    db.mark_interrupted_runs(con, (lock.holder() or {}).get("pid"))
    for r in con.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (args.n,)):
        print(f"run {r['id']}  {r['started_at'][:16]}  {r['origin']:<8} {r['kind']:<13} {r['status']:<11}"
              f" listed {r['posts_listed']}, fetched {r['posts_fetched']}, processed {r['posts_processed']},"
              f" noted {r['posts_noted']}, skipped {r['posts_skipped']}, ~${r['cost_estimate_usd']:.2f}"
              + (f"\n      {r['error']}" if r["error"] else ""))


def cmd_gold(args) -> None:
    """r2g gold merge [--dry-run]: fold ideas into the learnings they put into practice."""
    from . import gold, notes
    found = gold.plan()
    for pair in found["pairs"]:
        idea, learning = pair["idea"], pair["learning"]
        print(f"{idea['name']}\n  → {learning['name']}\n    “{idea['title']}” goes under Try it in “{learning['title']}”"
              + (f"\n    brings {len(pair['new_sources'])} more sources: {', '.join(pair['new_sources'])}" if pair["new_sources"] else "")
              + (f"\n    also linked, not merged into: {'; '.join(pair['also_linked'])}" if pair["also_linked"] else ""))
    for idea in found["dropped"]:
        print(f"{idea['name']}\n  stays: you set it to dropped")
    for idea in found["alone"]:
        print(f"{idea['name']}\n  stays: no learning behind it, so it is a pure action")
    print(f"\n{len(found['pairs'])} ideas merge into {len({p['learning']['name'] for p in found['pairs']})} learnings;"
          f" {len(found['alone']) + len(found['dropped'])} stay as ideas.")
    if args.dry_run or not found["pairs"]:
        return
    if not args.yes and input("Merge them? Undo reverts it. [y/N] ").strip().lower() != "y":
        raise SystemExit("nothing merged")
    from .runs import recorded_run
    cfg = load()
    with recorded_run("terminal", "r2g gold merge", "gold-merge", [], cfg) as run:
        run.report.set_stage("merge")
        before = brain.snapshot()
        done = gold.merge(run.report)
        sha, changed = brain.finish(before, brain.idea_paths(), f"agent: merge {len(done)} ideas into their learnings (run {run.run_id})")
        notes.add_commit(run.con, run.run_id, sha)
        if sha:
            run.report(f"vault commit {sha}: {len(changed)} files")
        run.counts["learnings_updated"] = len({p["learning"]["name"] for p in done})
        run.report.set_stage("done")
    row = db.connect().execute("SELECT status, error FROM runs WHERE id = ?", (run.run_id,)).fetchone()
    print(f"run {run.run_id} {row['status']}" + (f": {row['error']}" if row["error"] else f": commit {sha or '-'}"))


def cmd_ideas(args) -> None:
    con = db.connect()
    if args.action == "list":
        print(f"{'Support':>7}  {'Status':<8}  {'Name':<44}  Title")
        for kind in ideas.KINDS:
            for item in ideas.list_items(kind):
                print(f"{item['support']:>7}  {item['status']:<8}  {item['name']:<44}  {item['title']}")
        return
    if args.action == "themes":
        pending = {Path(r[0]).stem for r in con.execute(
            "SELECT note_path FROM posts WHERE status = 'done'"
            f" AND ({ideas.unchecked_sql()}) AND note_path IS NOT NULL")}
        for theme, names in ideas.themes().items():
            unchecked = len(set(names) & pending)
            print(f"{theme}: {unchecked} of {len(names)} not checked")
        return
    from .runs import recorded_run
    cfg = load()
    if args.action == "apply":
        with recorded_run("terminal", "r2g ideas apply", "ideas", [], cfg) as run:
            run.report.set_stage("ideas")
            try:
                done = ideas.apply_dry_run(run.con, args.run_id, run.report, run.run_id)
            except ValueError as exc:
                raise SystemExit(str(exc)) from None
            run.counts.update(done["counts"])
            run.report.set_stage("done")
        marked = {pid for _, key in ideas.CHECKS.values() for pid in done[key]}
        print(f"applied dry run {args.run_id}: {len(done['copied'])} ideas, learnings and events copied,"
              f" {len(done['skipped'])} skipped, {len(marked)} notes marked checked; commit {done['commit'] or '-'}")
        return
    ids = conn_ids(args.conn) if args.action == "pass" else None
    chosen = ([x.strip() for x in args.themes.split(",") if x.strip()] if args.themes else None)
    try:
        todo = ideas.candidates_new(con, ids, cfg=cfg) if args.action == "pass" else ideas.candidates_rebuild(con, chosen)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    if args.action == "rebuild" and args.limit is not None:
        todo = todo[:max(0, args.limit)]
    kind = "ideas-dry-run" if args.dry_run else "ideas"
    with recorded_run(args.origin, f"r2g ideas {args.action}", kind, ids, cfg) as run:
        run.report(f"run {run.run_id}: {len(todo)} notes to consider")
        if not args.dry_run:
            vault.prepare_and_report(cfg, run.report)
        run.report.set_stage("ideas")
        if todo:
            api_key = ai.api_key(cfg)
            result = ideas.run_pass(run.con, todo, cfg, run.report, run.run_id, args.dry_run, api_key)
            run.counts.update(ideas.counts(result))
        run.report.set_stage("done")
    row = run.row()
    print(f"run {row['id']} {row['status']}: ideas created {row['ideas_created']}, updated {row['ideas_updated']};"
          f" learnings created {row['learnings_created']}, updated {row['learnings_updated']};"
          f" events created {row['events_created']}, updated {row['events_updated']}"
          + (f"; {row['error']}" if row["error"] else ""))
    if row["status"] == "failed":
        raise SystemExit(1)


def locked(command: str, fn, *a, **kw):
    """Run a pipeline stage while holding the lock, so the app and the terminal can't run at the same time."""
    with lock.PipelineLock("terminal", command):
        return fn(*a, **kw)


def cmd_undo(args):
    row = db.connect().execute("SELECT brain_commits FROM runs WHERE id = ?", (args.run_id,)).fetchone()
    if not row:
        raise SystemExit(f"No run {args.run_id}.")
    if not args.yes:
        answer = input(f"Undo run {args.run_id} and its vault commits {row['brain_commits'] or '(none)'}? [y/N] ")
        if answer.strip().lower() != "y":
            raise SystemExit("Not undone.")
    from .runs import recorded_run
    with recorded_run("terminal", f"r2g undo {args.run_id}", "undo", [], load()) as run:
        run.report.set_stage("undo")
        undo.undo_run(run.con, args.run_id, run.report)
        run.report.set_stage("done")
    print(f"run {run.run_id} {run.row()['status']}")
    if run.row()["status"] == "failed":
        raise SystemExit(1)


def cmd_update(args):
    from .runs import recorded_run
    with recorded_run(args.origin, "r2g update-downloaders", "update", [], load()) as run:
        run.report.set_stage("update")
        downloaders.update(run.report)
        run.report.set_stage("done")
    print(f"run {run.run_id} {run.row()['status']}")
    if run.row()["status"] == "failed":
        raise SystemExit(1)


def ask(question: str, default: str = "") -> str:
    answer = input(f"{question}{f' [{default}]' if default else ''}: ").strip()
    return answer or default


def cmd_setup(args) -> None:
    """The setup page's questions, in the terminal."""
    from . import firstrun
    cfg = load()
    if args.check:
        for label, value in firstrun.summary(cfg):
            print(f"{label}: {value}")
        for c in firstrun.checks(cfg):
            print(f"[{'ok' if c['ok'] else '--'}] {c['name']}: {c['detail']}")
        return
    values = firstrun.form_defaults(cfg)
    vaults = firstrun.obsidian_vaults()
    for n, v in enumerate(vaults, start=1):
        print(f"  {n}. {v['name']}  ({v['path']})")
    pick = ask("Your Obsidian vault: a number above, or a folder" if vaults else "Your Obsidian vault folder", values["vault"])
    values["vault"] = vaults[int(pick) - 1]["path"] if pick.isdigit() and 0 < int(pick) <= len(vaults) else pick
    values["folder"] = ask("Folder for Rot2Gold in the vault" + (" (empty keeps your layout)" if not values["folder"] else ""),
                           values["folder"])
    values["data_dir"] = ask("Where to keep videos and other content", values["data_dir"])
    for key, label in ai.PROVIDERS.items():
        print(f"  {key}: {label}")
    values["provider"] = ask("Who writes the notes", values["provider"])
    if values["provider"] == "local":
        values["local_url"] = ask("Local server address", values["local_url"])
    values["model"] = ask("Model (empty: the provider's default)", values["model"])
    values["language"] = ask("Note language", values["language"])
    import getpass
    values["key"] = getpass.getpass("API key, only if you don't sign in to the tool (hidden; Enter to skip): ").strip()
    values["collection"] = ask("First TikTok collection link (optional)")
    values["launcher"] = ask("Add Rot2Gold to your app menu? (y/n)", "y" if values["launcher"] else "n").lower().startswith("y")
    changes, errors = firstrun.validate(values, cfg)
    if errors:
        raise SystemExit("\n".join(["Setup wasn't saved:", *errors]))
    firstrun.save(values, changes, cfg, report=print)
    print("Setup saved. Start the app with: r2g")


def main() -> None:
    if os.name == "nt" and not sys.flags.utf8_mode:
        # Windows reads and writes text in the local code page unless Python runs in UTF-8 mode:
        # run again in it, so notes keep their accents and emoji.
        os.environ["PYTHONUTF8"] = "1"
        raise SystemExit(subprocess.call([sys.executable, "-m", "rot2gold.cli", *sys.argv[1:]]))
    if hasattr(signal, "SIGBREAK"):  # Windows: Stop sends CTRL_BREAK; treat it like Ctrl+C (KeyboardInterrupt)
        signal.signal(signal.SIGBREAK, signal.default_int_handler)
    p = argparse.ArgumentParser(prog="r2g", description=__doc__)
    sub = p.add_subparsers(dest="cmd")  # no command: open the app
    sp = sub.add_parser("sync", help="list every connection (or those given) and add new posts")
    sp.add_argument("--conn", help="connection ids, comma-separated")
    for name, help_ in (("fetch", "download media for up to N posts"),
                        ("process", "OCR and transcribe up to N fetched posts"),
                        ("run", "sync + fetch + process")):
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("n", nargs="?", type=int)
    sp = sub.add_parser("extract", help="the whole pipeline for connections: sync, fetch, process, write notes")
    sp.add_argument("--conn", help="connection ids, comma-separated (default: all)")
    sp.add_argument("--max-notes", type=int, help="write at most this many notes (default: config.toml [notes])")
    sp.add_argument("--no-notes", action="store_true", help="stop after OCR and transcription")
    sp.add_argument("--no-ideas", action="store_true", help="skip the ideas pass")
    sp.add_argument("--origin", default="terminal", choices=("terminal", "app"), help=argparse.SUPPRESS)
    sp.add_argument("--quiet", action="store_true", help=argparse.SUPPRESS)
    sp = sub.add_parser("conn", help="manage connections (collections)")
    csub = sp.add_subparsers(dest="action", required=True)
    csub.add_parser("list", help="list connections with post counts")
    cp = csub.add_parser("add", help="add a connection")
    cp.add_argument("url")
    cp.add_argument("--name")
    cp.add_argument("--platform", default="tiktok")
    cp.add_argument("--cookies", default="auto", choices=connections.COOKIE_MODES)
    cp.add_argument("--browser", default="firefox", choices=connections.BROWSERS, help="browser to read login cookies from")
    cp = csub.add_parser("edit", help="change a connection")
    cp.add_argument("id", type=int)
    cp.add_argument("--name")
    cp.add_argument("--url")
    cp.add_argument("--cookies", choices=connections.COOKIE_MODES)
    cp.add_argument("--browser", choices=connections.BROWSERS, help="browser to read login cookies from")
    cp.add_argument("--profile", help="browser profile for cookies ('' = the browser's default)")
    cp = csub.add_parser("rm", help="delete a connection (posts and notes stay)")
    cp.add_argument("id", type=int)
    cp.add_argument("--yes", action="store_true")
    cp = csub.add_parser("links", help="replace a connection's hand-pasted post URLs (read from stdin)")
    cp.add_argument("id", type=int)
    sp = sub.add_parser("ideas", help="list ideas, learnings and events, themes, or run the pass that finds them")
    isub = sp.add_subparsers(dest="action", required=True)
    isub.add_parser("list")
    isub.add_parser("themes")
    ip = isub.add_parser("apply", help="copy a reviewed dry run into the vault (no new AI call)")
    ip.add_argument("run_id", type=int)
    ip = isub.add_parser("pass")
    ip.add_argument("--conn", help="connection ids, comma-separated")
    ip = isub.add_parser("rebuild")
    ip.add_argument("--themes", help="comma-separated theme names")
    ip.add_argument("--limit", type=int)
    for ip in (isub.choices["pass"], isub.choices["rebuild"]):
        ip.add_argument("--dry-run", action="store_true")
        ip.add_argument("--origin", default="terminal", choices=("terminal", "app"), help=argparse.SUPPRESS)
    sp = sub.add_parser("gold", help="Gold: fold ideas into the learnings they put into practice")
    gsub = sp.add_subparsers(dest="action", required=True)
    gp = gsub.add_parser("merge", help="move each idea's action under its learning's Try it (one commit; Undo reverts it)")
    gp.add_argument("--dry-run", action="store_true", help="only show what would merge")
    gp.add_argument("--yes", action="store_true")
    sp = sub.add_parser("ui", help="start the app at http://127.0.0.1:8740 (the default when no command is given)")
    sp.add_argument("--no-browser", action="store_true")
    sp = sub.add_parser("setup", help="choose the vault, folders and AI in the terminal (the app asks the same on first start)")
    sp.add_argument("--check", action="store_true", help="only show where things are and what is installed")
    sp = sub.add_parser("undo", help="revert one finished run's vault commits and reopen its posts")
    sp.add_argument("run_id", type=int)
    sp.add_argument("--yes", action="store_true")
    sp = sub.add_parser("update-downloaders", help="upgrade yt-dlp and gallery-dl")
    sp.add_argument("--origin", default="terminal", choices=("terminal", "app"), help=argparse.SUPPRESS)
    sub.add_parser("install-launcher", help="add the app to your app menu (Linux, macOS, Windows)")
    sub.add_parser("uninstall-launcher", help="remove the app launcher")
    sp = sub.add_parser("runs", help="recent runs")
    sp.add_argument("n", nargs="?", type=int, default=10)
    sp = sub.add_parser("pending", help="show processed posts waiting for a note")
    sp.add_argument("n", nargs="?", type=int)
    sp.add_argument("--id", help="show one post (any status)")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("--ids", action="store_true", help="print only the ids")
    sp = sub.add_parser("done", help="mark a post as written up")
    sp.add_argument("id")
    sp.add_argument("note_path")
    sp = sub.add_parser("skip", help="skip a post with a reason")
    sp.add_argument("id")
    sp.add_argument("reason")
    sub.add_parser("status", help="counts by status and skip reason")
    args = p.parse_args()

    try:
        if args.cmd == "sync":
            from .sync import sync
            locked("r2g sync", sync, conn_ids(args.conn))
        elif args.cmd == "fetch":
            from .fetch import fetch
            locked("r2g fetch", fetch, args.n)
        elif args.cmd == "process":
            from .process import process
            locked("r2g process", process, args.n)
        elif args.cmd == "run":
            from .fetch import fetch
            from .process import process
            from .sync import sync
            with lock.PipelineLock("terminal", "r2g run"):
                sync()
                fetch(args.n)
                process(args.n)
        elif args.cmd == "extract":
            from .extract import extract
            run = extract(conn_ids(args.conn), origin=args.origin, max_notes=args.max_notes,
                          write=not args.no_notes, quiet=args.quiet, find_ideas=not args.no_ideas)
            print(f"run {run['id']} {run['status']}: listed {run['posts_listed']}, fetched {run['posts_fetched']},"
                  f" processed {run['posts_processed']}, noted {run['posts_noted']}, skipped {run['posts_skipped']}"
                  f"; ~${run['cost_estimate_usd']:.2f} API-equivalent")
            if run["status"] == "failed":
                raise SystemExit(1)
        elif args.cmd in ("ui", None):
            from .web.app import serve
            serve(open_browser=not getattr(args, "no_browser", False))
        elif args.cmd == "setup":
            cmd_setup(args)
        elif args.cmd == "ideas":
            cmd_ideas(args)
        elif args.cmd == "gold":
            cmd_gold(args)
        elif args.cmd == "undo":
            cmd_undo(args)
        elif args.cmd == "update-downloaders":
            cmd_update(args)
        elif args.cmd == "install-launcher":
            print("Installed launcher:", launcher.install()[0])
        elif args.cmd == "uninstall-launcher":
            launcher.uninstall()
            print("Removed launcher.")
        else:
            {"pending": cmd_pending, "done": cmd_done, "skip": cmd_skip, "status": cmd_status,
             "conn": cmd_conn, "runs": cmd_runs}[args.cmd](args)
    except VNError as exc:
        raise SystemExit(f"{exc}") from None
    except KeyboardInterrupt:
        raise SystemExit("stopped") from None


def conn_ids(text: str | None) -> list[int] | None:
    if not text:
        return None
    try:
        return [int(x) for x in text.split(",") if x.strip()]
    except ValueError:
        raise SystemExit("--conn takes connection ids like 1,2 (see `r2g conn list`)") from None


if __name__ == "__main__":
    main()
