"""The local web app: `vn ui` → http://127.0.0.1:8740.

Pages are rendered on the server. A run is never executed inside this server: Extract starts
`vn extract --origin app` as its own process, and the run page streams its run_events over
Server-Sent Events. So closing the tab or restarting the server doesn't stop a run.
"""

import json
import os
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import brain, connections, db, ideas, lock, notefile, sources
from ..config import DATA, LOGS, MEDIA, ROOT, load, media_dir
from ..errors import VNError

APP_NAME = "video-notes-app"  # the project name may change: this is the only place the UI shows it
HERE = Path(__file__).parent
HOST = "127.0.0.1"  # loopback only: reachable from this laptop, never from the network

app = FastAPI(title=APP_NAME, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
children: list[subprocess.Popen] = []  # runs started here; polled so finished ones don't linger as zombies


def local_time(iso: str | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    if not iso:
        return ""
    return datetime.fromisoformat(iso).astimezone().strftime(fmt)


def plan_windows(plan_json: str | None) -> list[dict]:
    """[{name, used, resets}] from a run's stored rate_limit_info."""
    if not plan_json:
        return []
    windows = (json.loads(plan_json).get("unifiedWindows") or {})
    out = []
    for key, name in (("five_hour", "5-hour window"), ("seven_day", "7-day window")):
        w = windows.get(key)
        if w and w.get("utilization") is not None:
            out.append({"name": name, "used": w["utilization"],
                        "resets": datetime.fromtimestamp(w["resetsAt"]).strftime("%a %H:%M") if w.get("resetsAt") else ""})
    return out


templates.env.filters["local_time"] = local_time
templates.env.globals.update(APP_NAME=APP_NAME, LABELS=connections.LABELS, STATUSES=connections.STATUSES,
                             plan_windows=plan_windows)


def active_run(con) -> dict | None:
    """The run holding the lock right now (app or terminal), with its runs row if it has one."""
    for p in list(children):
        if p.poll() is not None:
            children.remove(p)
    info = lock.holder()
    db.mark_interrupted_runs(con, (info or {}).get("pid"))
    if info is None:
        return None
    row = con.execute("SELECT * FROM runs WHERE id = ?", (info.get("run_id"),)).fetchone() if info.get("run_id") else None
    return {"lock": info, "who": lock.describe(info), "run": dict(row) if row else None}


def page(request: Request, name: str, **ctx) -> HTMLResponse:
    con = db.connect()
    ctx.setdefault("active", active_run(con))
    ctx |= {"msg": request.query_params.get("msg"), "err": request.query_params.get("err")}
    return templates.TemplateResponse(request, name, ctx)


def back(path: str = "/", **params) -> RedirectResponse:
    params = {k: v for k, v in params.items() if v}
    return RedirectResponse(path + ("?" + urlencode(params) if params else ""), status_code=303)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    con = db.connect()
    cfg = load()
    last = con.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    return page(request, "connections.html", conns=connections.all_with_counts(con), sources=sources.SOURCES,
                cookie_modes=connections.COOKIE_MODES, notes_cfg=cfg["notes"], last=dict(last) if last else None,
                links={c["id"]: "\n".join(connections.links(con, c["id"]))
                       for c in con.execute("SELECT id FROM connections")})


@app.post("/connections")
def add_connection(platform: str = Form(...), url: str = Form(...), name: str = Form(""),
                   cookies_mode: str = Form("auto")):
    try:
        cid = connections.add(db.connect(), platform, url, name, cookies_mode)
    except ValueError as exc:
        return back(err=str(exc))
    return back(msg=f"Connection added. Select it and press Extract.", added=cid)


@app.post("/connections/{cid}")
def edit_connection(cid: int, name: str = Form(""), url: str = Form(""), cookies_mode: str = Form("auto"),
                    firefox_profile: str = Form(""), links: str = Form("")):
    con = db.connect()
    try:
        connections.update(con, cid, name=name, url=url, cookies_mode=cookies_mode, firefox_profile=firefox_profile)
        kept = connections.set_links(con, cid, links)
    except ValueError as exc:
        return back(err=str(exc))
    return back(msg="Connection saved." + (f" {kept} post URLs saved for when listing fails." if kept else ""))


@app.get("/connections/{cid}/delete", response_class=HTMLResponse)
def confirm_delete(request: Request, cid: int):
    con = db.connect()
    try:
        conn = dict(connections.get(con, cid))
    except ValueError as exc:
        return back(err=str(exc))
    return page(request, "delete.html", conn=conn, counts=connections.counts(con, cid),
                only_here=connections.only_here(con, cid))


@app.post("/connections/{cid}/delete")
def delete_connection(cid: int):
    try:
        connections.delete(db.connect(), cid)
    except ValueError as exc:
        return back(err=str(exc))
    return back(msg="Connection deleted. Its posts, media and notes are still there.")


@app.post("/extract")
def start_extract(conn: list[int] = Form([]), max_notes: str = Form(""), write_notes: str = Form(""),
                  find_ideas: str = Form("")):
    if not conn:
        return back(err="Select at least one connection to extract.")
    cmd = [sys.executable, "-m", "video_notes.cli", "extract", "--origin", "app", "--conn", ",".join(map(str, conn))]
    if max_notes.strip().isdigit():
        cmd += ["--max-notes", max_notes.strip()]
    if not write_notes:
        cmd.append("--no-notes")
    if not find_ideas:
        cmd.append("--no-ideas")
    return spawn_run(cmd, "Extract")


def spawn_run(cmd: list[str], label: str):
    """Start an independent recorded run and wait for its lock record."""
    if info := lock.holder():
        return back(err=f"The pipeline is already running: {lock.describe(info)}.")
    LOGS.mkdir(parents=True, exist_ok=True)
    log = LOGS / f"{label.lower()}-{datetime.now():%Y%m%d-%H%M%S}.log"
    env = dict(os.environ)
    # The note-writing agent calls `vn`: make sure it's on PATH even if the app was started from a launcher.
    env["PATH"] = os.pathsep.join([str(ROOT / ".venv/bin"), str(Path.home() / ".local/bin"), env.get("PATH", "")])
    with open(log, "w") as out:
        # start_new_session: the run gets its own process group, so Stop can signal it and all its children.
        proc = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                start_new_session=True)
    children.append(proc)
    for _ in range(50):  # wait up to 5 s for the run to take the lock and create its runs row
        info = lock.holder()
        if info and info.get("pid") == proc.pid and info.get("run_id"):
            return back(f"/runs/{info['run_id']}")
        if proc.poll() is not None:
            tail = log.read_text().strip().splitlines()[-3:]
            return back(err=f"{label} stopped right away: " + " ".join(tail))
        time.sleep(0.1)
    return back(msg=f"{label} is starting…")


@app.post("/runs/stop")
def stop_run():
    info = lock.holder()
    if not info:
        return back(msg="Nothing is running.")
    try:
        # SIGINT is the polite "please stop" (like Ctrl+C): downloads stop after the current post,
        # claude ends its turn, and the run records what it finished.
        os.killpg(os.getpgid(info["pid"]), signal.SIGINT)
    except ProcessLookupError:
        return back(msg="The run had already ended.")
    return back(f"/runs/{info['run_id']}" if info.get("run_id") else "/", msg="Stopping… the current step finishes first.")


def note_head(row) -> dict:
    """Title and description of a post's note, read from the brain ({} if it has none)."""
    if row["status"] != "done" or not row["note_path"]:
        return {}
    path = brain.note_file(row["note_path"])
    if not path.is_file():
        return {"missing": True}
    note = notefile.read(path, head_only=True)
    return {"title": note.title, "description": note.meta.get("description", "")}


def note_links(con):
    """Resolve wikilinks to video pages or Obsidian, leaving unknown names as text."""
    names = notefile.brain_names()
    videos_by_note = {Path(r["note_path"]).stem: r["id"] for r in
                      con.execute("SELECT id, note_path FROM posts WHERE note_path IS NOT NULL")}

    def link_for(name):
        if name not in names:
            return None
        if name in videos_by_note:
            return f"/videos/{videos_by_note[name]}"
        return notefile.obsidian_link(names[name])

    return link_for


@app.get("/videos", response_class=HTMLResponse)
def videos(request: Request, conn: str = "", status: str = "", type: str = "", q: str = ""):
    con = db.connect()
    where, args = [], []
    if conn.isdigit():
        where.append("EXISTS (SELECT 1 FROM connection_posts x WHERE x.post_id = p.id AND x.connection_id = ?)")
        args.append(int(conn))
    base_where, base_args = list(where), list(args)  # status counts ignore the status filter itself
    if status in connections.STATUSES:
        where.append("p.status = ?")
        args.append(status)
    if type in ("video", "slideshow"):
        where.append("p.type = ?")
        args.append(type)
    sql = ("SELECT p.*, GROUP_CONCAT(cp.connection_id) AS conns FROM posts p"
           " LEFT JOIN connection_posts cp ON cp.post_id = p.id"
           + (" WHERE " + " AND ".join(where) if where else "") +
           " GROUP BY p.id ORDER BY COALESCE(p.upload_date, '') DESC, p.rowid DESC")
    rows = []
    needle = q.strip().lower()
    for r in con.execute(sql, args):
        item = dict(r) | note_head(r)
        item["conn_ids"] = [int(x) for x in (r["conns"] or "").split(",") if x]
        if needle and needle not in " ".join(str(item.get(k) or "") for k in
                                             ("id", "creator", "title", "description", "skip_reason")).lower():
            continue
        rows.append(item)
    counts = dict.fromkeys(connections.STATUSES, 0)
    for r in con.execute("SELECT p.status, COUNT(*) n FROM posts p" + (" WHERE " + " AND ".join(base_where) if base_where else "")
                         + " GROUP BY p.status", base_args):
        counts[r["status"]] = r["n"]
    names = {r["id"]: r["name"] for r in con.execute("SELECT id, name FROM connections ORDER BY id")}
    return page(request, "videos.html", rows=rows, counts=counts, names=names,
                f={"conn": conn, "status": status, "type": type, "q": q})


@app.get("/videos/{post_id}", response_class=HTMLResponse)
def video(request: Request, post_id: str):
    con = db.connect()
    row = con.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    if not row:
        return back("/videos", err=f"No post {post_id}.")
    post = dict(row)
    images = [dict(i) | {"url": f"/media/{post_id}/{Path(i['path']).name}"}
              for i in con.execute("SELECT * FROM images WHERE post_id = ? ORDER BY idx", (post_id,))]
    segments = [dict(s) for s in con.execute("SELECT * FROM segments WHERE post_id = ? ORDER BY idx", (post_id,))]
    conns = [dict(c) for c in con.execute("SELECT c.id, c.name FROM connections c JOIN connection_posts cp"
                                         " ON cp.connection_id = c.id WHERE cp.post_id = ? ORDER BY c.id", (post_id,))]
    note = note_html = obsidian = None
    if post["note_path"] and (path := brain.note_file(post["note_path"])).is_file():
        note = notefile.read(path)
        note_html = notefile.render(note.body, note_links(con))
        obsidian = notefile.obsidian_link(path)
    return page(request, "video.html", post=post, images=images, segments=segments, conns=conns,
                note=note, note_html=note_html, obsidian=obsidian)


@app.get("/media/{post_id}/{name}")
def media(post_id: str, name: str):
    """Frame and slide images, only from inside data/media/."""
    path = (media_dir(post_id) / name).resolve()
    if not path.is_relative_to(MEDIA.resolve()) or not path.is_file():
        return HTMLResponse("Not found", status_code=404)
    return FileResponse(path)


def idea_rows(con, folder=None):
    link_for = note_links(con)
    return [item | {"source_links": [{"name": name, "url": link_for(name)} for name in item["sources"]],
                    "obsidian": notefile.obsidian_link(item["path"]) if folder is None else None}
            for item in ideas.list_ideas(folder)]


@app.get("/ideas", response_class=HTMLResponse)
def idea_index(request: Request, status: str = "all", q: str = ""):
    con = db.connect()
    rows = idea_rows(con)
    if status in ("new", "trying", "kept", "dropped"):
        rows = [r for r in rows if r["status"] == status]
    if q.strip():
        rows = [r for r in rows if q.strip().lower() in
                " ".join(str(r[k]) for k in ("title", "description", "name")).lower()]
    pending = {Path(r["note_path"]).stem for r in con.execute(
        "SELECT note_path FROM posts WHERE status = 'done' AND note_path IS NOT NULL AND ideas_checked_at IS NULL")}
    themes = [{"name": name, "total": len(names), "unchecked": len(set(names) & pending)}
              for name, names in ideas.themes().items()]
    return page(request, "ideas.html", rows=rows, themes=themes, status=status, q=q)


@app.post("/ideas/rebuild")
def start_ideas_rebuild(themes: list[str] = Form([]), dry_run: str = Form(""), limit: str = Form("")):
    cmd = [sys.executable, "-m", "video_notes.cli", "ideas", "rebuild", "--origin", "app"]
    if themes:
        cmd += ["--themes", ",".join(themes)]
    if dry_run:
        cmd.append("--dry-run")
    if limit.strip().isdigit():
        cmd += ["--limit", limit.strip()]
    return spawn_run(cmd, "Ideas")


@app.get("/ideas/preview/{run_id}", response_class=HTMLResponse)
def idea_preview(request: Request, run_id: int):
    con = db.connect()
    run = con.execute("SELECT kind FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not run or run["kind"] != "ideas-dry-run":
        return HTMLResponse("Not found", status_code=404)
    root = (DATA / "ideas-dry-run").resolve()
    folder = (root / f"run-{run_id}").resolve()
    if not folder.is_relative_to(root):
        return HTMLResponse("Not found", status_code=404)
    rows = idea_rows(con, folder) if folder.is_dir() else []
    for item in rows:
        note = notefile.read(item["path"])
        item["html"] = notefile.render(note.body, note_links(con))
        item["is_update"] = (ideas.ideas_dir() / item["path"].name).is_file()
    manifest = ideas.read_manifest(folder) if folder.is_dir() else {}
    return page(request, "idea-preview.html", rows=rows, run_id=run_id, manifest=manifest)


@app.post("/ideas/preview/{run_id}/apply")
def apply_preview(run_id: int):
    """Quick (no AI): runs in the request, but still under the pipeline lock."""
    from ..runs import recorded_run
    try:
        with recorded_run("app", "vn ideas apply", "ideas", [], load()) as run:
            run.report.set_stage("ideas")
            done = ideas.apply_dry_run(run.con, run_id, run.report)
            run.counts["ideas_created"] = len(done["copied"])
            run.report.set_stage("done")
    except (ValueError, VNError) as exc:
        return back(f"/ideas/preview/{run_id}", err=str(exc))
    return back("/ideas", msg=f"Applied dry run {run_id}: {len(done['copied'])} ideas written to the brain"
                + (f", {len(done['skipped'])} skipped because you changed them since" if done["skipped"] else "")
                + (f" (commit {done['commit']})" if done["commit"] else "") + ".")


@app.get("/ideas/{name}", response_class=HTMLResponse)
def idea_detail(request: Request, name: str):
    if not name.startswith("idea-") or Path(name).name != name:
        return HTMLResponse("Not found", status_code=404)
    con = db.connect()
    item = next((r for r in idea_rows(con) if r["name"] == name), None)
    if not item:
        return HTMLResponse("Not found", status_code=404)
    note = notefile.read(item["path"])
    return page(request, "idea.html", idea=item, html=notefile.render(note.body, note_links(con)))


@app.get("/runs", response_class=HTMLResponse)
def runs(request: Request):
    con = db.connect()
    active = active_run(con)
    rows = [dict(r) for r in con.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 50")]
    names = {r["id"]: r["name"] for r in con.execute("SELECT id, name FROM connections")}
    return page(request, "runs.html", runs=rows, names=names, active=active)


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_page(request: Request, run_id: int):
    con = db.connect()
    active = active_run(con)
    row = con.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not row:
        return back("/runs", err=f"No run {run_id}.")
    events = [dict(e) for e in con.execute("SELECT * FROM run_events WHERE run_id = ? ORDER BY id", (run_id,))]
    names = {r["id"]: r["name"] for r in con.execute("SELECT id, name FROM connections")}
    return page(request, "run.html", run=dict(row), events=events, names=names, active=active,
                last_event=events[-1]["id"] if events else 0)


@app.get("/runs/{run_id}/events")
def run_events(run_id: int, after: int = 0):
    """Server-Sent Events: each new run_events row as a `data:` line, then `end` when the run is over."""
    def stream():
        con = db.connect()
        last, idle, seen = after, 0, None
        while True:
            rows = con.execute("SELECT * FROM run_events WHERE run_id = ? AND id > ? ORDER BY id", (run_id, last)).fetchall()
            for r in rows:
                last = r["id"]
                yield f"id: {r['id']}\ndata: {json.dumps(dict(r))}\n\n"
            run = con.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            if run is not None and tuple(run) != seen:  # counts, stage or usage changed
                seen = tuple(run)
                yield f"event: run\ndata: {json.dumps(dict(run))}\n\n"
            if run is None or (run["status"] != "running" and not rows):
                yield f"event: end\ndata: {json.dumps(dict(run) if run else {})}\n\n"
                return
            if run["status"] == "running" and not rows:
                idle += 1
                if idle % 30 == 0:  # every ~15 s: check the run's process is still alive
                    db.mark_interrupted_runs(con, (lock.holder() or {}).get("pid"))
                    yield ": keep-alive\n\n"
            else:
                idle = 0
            time.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


def serve(open_browser: bool = True) -> None:
    import uvicorn
    port = int(load()["app"]["port"])
    url = f"http://{HOST}:{port}"
    print(f"{APP_NAME} at {url}  (Ctrl+C to stop the server; a running Extract keeps going)")
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=HOST, port=port, log_level="warning")
