"""The local web app: `r2g ui` → http://127.0.0.1:8740.

Pages are rendered on the server. A run is never executed inside this server: Extract starts
`r2g extract --origin app` as its own process, and the run page streams its run_events over
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
import socket
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import brain, connections, db, delete, downloaders, ideas, lock, notefile, secrets, settings, sources, undo
from ..ai import claude_cli
from ..config import DATA, LOGS, MEDIA, ROOT, brain_dir, load, media_dir
from ..errors import VNError

APP_NAME = "Rot2Gold"  # the only place the UI shows the name
HERE = Path(__file__).parent
HOST = "127.0.0.1"  # loopback only: reachable from this laptop, never from the network

app = FastAPI(title=APP_NAME, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
children: list[subprocess.Popen] = []  # runs started here; polled so finished ones don't linger as zombies
server = None


@app.middleware("http")
async def local_requests(request: Request, call_next):
    port = int(load()["app"]["port"])
    allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
    if request.headers.get("host", "").lower() not in allowed:
        return PlainTextResponse("Use the local app address.", status_code=400)
    if request.method not in ("GET", "HEAD"):
        source = request.headers.get("origin") or request.headers.get("referer", "")
        parts = urlsplit(source)
        if parts.scheme != "http" or parts.netloc.lower() not in allowed:
            return PlainTextResponse("This action must come from the app's own page.", status_code=403)
    return await call_next(request)


def local_time(iso: str | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    if not iso:
        return ""
    return datetime.fromisoformat(iso).astimezone().strftime(fmt)


def relative_time(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        day = datetime.fromisoformat(iso).astimezone().date()
        today = datetime.now().astimezone().date()
        if day == today:
            return "today " + local_time(iso, "%H:%M")
        if (today - day).days == 1:
            return "yesterday"
        return local_time(iso, "%d %b %Y")
    except ValueError:
        return iso


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


RUN_TITLES = {"extract": "Extract", "ideas": "Ideas, learnings and events from older notes",
              "ideas-dry-run": "Ideas, learnings and events preview",
              "update": "Downloader update", "undo": "Undo", "delete": "Deleted an idea"}


def plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def run_title(run: dict, names: dict) -> str:
    """"Extract · Material", "Ideas from older notes", …"""
    title = RUN_TITLES.get(run.get("kind"), (run.get("kind") or "Run").capitalize())
    if run.get("kind") == "delete" and run.get("deleted_kind") in ("learning", "event"):
        title = f"Deleted {'a learning' if run['deleted_kind'] == 'learning' else 'an event'}"
    picked = [names.get(int(i), "a deleted collection") for i in (run.get("connection_ids") or "").split(",") if i.isdigit()]
    return f"{title} · {', '.join(picked)}" if run.get("kind") == "extract" and picked else title


def run_summary(run: dict) -> str:
    """What a run did, in one sentence of plain words."""
    kind, status = run.get("kind"), run.get("status")
    if kind == "extract":
        parts = [f"checked {plural(run['posts_listed'], 'video')}" if run["posts_listed"] else "",
                 f"wrote {plural(run['posts_noted'], 'note')}" if run["posts_noted"] else "no new notes",
                 f"skipped {run['posts_skipped']}" if run["posts_skipped"] else "",
                 ideas_phrase(run)]
    elif kind and kind.startswith("ideas"):
        parts = [ideas_phrase(run) + (" proposed for review" if kind == "ideas-dry-run" and
                                      any(run.get(key) for key in ideas.COUNTERS) else "")]
    elif kind == "update":
        parts = ["downloaders updated" if status == "ok" else "downloaders not updated"]
    elif kind == "delete":
        gone = run.get("posts_skipped") or 0
        parts = [(f"{run.get('deleted_kind') or 'idea'} deleted" + (f" with {plural(gone, 'video')}" if gone else ""))
                 if status == "ok" else "nothing was deleted"]
    elif kind == "undo":
        parts = ["brain changes reverted" if status == "ok" else "nothing was reverted"]
    else:
        parts = []
    text = ", ".join(p for p in parts if p)
    return text[:1].upper() + text[1:] + "." if text else ""


def ideas_phrase(run: dict) -> str:
    """"2 new ideas, 1 learning updated and 3 new events", or "no new ideas, learnings or events"."""
    parts = []
    for kind in ideas.KINDS:
        created, updated = run.get(f"{kind}s_created") or 0, run.get(f"{kind}s_updated") or 0
        if created:
            parts.append(plural(created, f"new {kind}"))
        if updated:
            parts.append(f"{plural(updated, kind)} updated")
    if not parts:
        return "no new ideas, learnings or events"
    return ", ".join(parts[:-1]) + " and " + parts[-1] if len(parts) > 1 else parts[0]


def deleted_kind(con, run: dict) -> dict:
    """A delete run, marked with what it deleted, so History can say "Deleted a learning"."""
    if run.get("kind") == "delete":
        found = con.execute("SELECT message FROM run_events WHERE run_id = ? AND (message LIKE 'deleted learning %'"
                            " OR message LIKE 'deleted event %') LIMIT 1", (run["id"],)).fetchone()
        run["deleted_kind"] = found["message"].split()[1] if found else "idea"
    return run


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def event_date(when: str, until: str = "") -> str:
    """'2026-11-12' → '12 Nov 2026'; with until '2026-11-14' → '12–14 Nov 2026'; '2026-11' → 'Nov 2026'."""
    def parts(value):
        bits = (value or "").split("-")
        if not ideas.DATE.fullmatch(value or "") or (len(bits) > 1 and not 1 <= int(bits[1]) <= 12):
            return None
        return [bits[0], MONTHS[int(bits[1]) - 1] if len(bits) > 1 else "", str(int(bits[2])) if len(bits) > 2 else ""]
    start, end = parts(when), parts(until)
    if not start:
        return "Date unknown"
    show = lambda p, year=True: " ".join(x for x in (p[2], p[1], p[0] if year else "") if x)
    if not end or end == start:
        return show(start)
    if start[0] == end[0] and start[1] == end[1] and start[2] and end[2]:
        return f"{start[2]}–{show(end)}"
    return f"{show(start, year=start[0] != end[0])} – {show(end)}"


def asset_version() -> str:
    """Changes whenever style.css or app.js changes, so browsers never keep a stale copy."""
    return str(int(max((HERE / "static" / name).stat().st_mtime for name in ("style.css", "app.js"))))


templates.env.filters["local_time"] = local_time
templates.env.filters["relative_time"] = relative_time
templates.env.filters["event_date"] = event_date
templates.env.globals.update(APP_NAME=APP_NAME, LABELS=connections.LABELS, STATUSES=connections.STATUSES,
                             plan_windows=plan_windows, asset_version=asset_version, run_summary=run_summary)


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
    last = con.execute("SELECT id, message FROM run_events WHERE run_id = ? ORDER BY id DESC LIMIT 1",
                       (info.get("run_id"),)).fetchone() if row else None
    return {"lock": info, "who": lock.describe(info), "run": dict(row) if row else None,
            "last_event": last["id"] if last else 0, "last_line": last["message"] if last else ""}


def page(request: Request, name: str, **ctx) -> HTMLResponse:
    con = db.connect()
    ctx.setdefault("active", active_run(con))
    conns = connections.all_with_counts(con)
    last_runs = {}
    for run in con.execute("SELECT * FROM runs WHERE kind = 'extract' ORDER BY id DESC"):
        for raw_id in (run["connection_ids"] or "").split(","):
            if raw_id.isdigit() and int(raw_id) not in last_runs:
                last_runs[int(raw_id)] = dict(run)
    for item in conns:
        item["last_run"] = last_runs.get(item["id"])
        item["waiting"] = sum(item["counts"][s] for s in ("new", "fetched", "processed"))
    from ..sources.firefox import profiles
    ctx |= {"sidebar_conns": conns, "sidebar_links": {c["id"]: "\n".join(connections.links(con, c["id"])) for c in conns},
            "source_types": sources.SOURCES, "cookie_modes": connections.COOKIE_MODES,
            "firefox_profiles": profiles(), "notes_cfg": load()["notes"],
            "idea_count": len(ideas.list_ideas()), "learning_count": len(ideas.list_learnings()),
            "event_count": len(ideas.list_events()), "post_count": con.execute("SELECT COUNT(*) FROM posts").fetchone()[0]}
    ctx |= {"msg": request.query_params.get("msg"), "err": request.query_params.get("err")}
    return templates.TemplateResponse(request, name, ctx)


def back(path: str = "/", **params) -> RedirectResponse:
    params = {k: v for k, v in params.items() if v}
    return RedirectResponse(path + ("?" + urlencode(params) if params else ""), status_code=303)


def back_to(request: Request, fallback: str = "/ideas", drop: tuple = (), **params) -> RedirectResponse:
    """Redirect to the page the request came from (same origin only), with new msg/err params.

    `drop` removes query params that no longer make sense, e.g. the filter of a deleted collection.
    """
    from urllib.parse import parse_qsl
    source = urlsplit(request.headers.get("referer", ""))
    port = load()["app"]["port"]
    same_origin = source.scheme == "http" and source.netloc.lower() in {f"127.0.0.1:{port}", f"localhost:{port}"}
    path = source.path if same_origin else fallback
    if not path.startswith("/") or path.startswith("//") or path in ("/settings/panel", "/quit"):
        path = fallback
    stale = {"settings", "msg", "err", "added", *drop}
    query = {k: v for k, v in parse_qsl(source.query) if k not in stale} if same_origin else {}
    query.update({k: v for k, v in params.items() if v})
    return back(path, **query)


def settings_back(request: Request, tab: str, **params) -> RedirectResponse:
    """Back to the page with the Settings card reopened on `tab`, showing the result."""
    return back_to(request, settings=tab, **params)


@app.get("/healthz")
async def healthz():
    return {"app": APP_NAME}


def settings_context():
    cfg = load()
    con = db.connect()
    latest = con.execute("SELECT plan_usage FROM runs WHERE plan_usage IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
    try:
        key_set, key_error = secrets.has_api_key(), None
    except VNError as exc:
        key_set, key_error = False, str(exc)
    from ..sources.firefox import profiles
    return dict(fields=settings.EDITABLE, cfg=cfg, key_set=key_set, key_error=key_error,
                windows=plan_windows(latest[0] if latest else None), versions=downloaders.versions(),
                brain_path=brain_dir(cfg), port=cfg["app"]["port"], profiles=profiles())


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return page(request, "settings.html", **settings_context())


@app.get("/settings/panel", response_class=HTMLResponse)
async def settings_panel(request: Request):
    return templates.TemplateResponse(request, "_settings_panel.html", settings_context() | {"active": active_run(db.connect())})


@app.post("/settings")
async def save_settings(request: Request):
    form = await request.form()
    values = {f"{f['section']}.{f['key']}": form.get(f"{f['section']}.{f['key']}", "") for f in settings.EDITABLE}
    if values["notes.backend"] == "api" and not secrets.has_api_key():
        return settings_back(request, "general", err="Set an API key before selecting the API backend.")
    errors = settings.save(values)
    return settings_back(request, "general", err="; ".join(errors)) if errors else settings_back(request, "general", msg="Settings saved.")


@app.post("/settings/key")
def set_key(request: Request, key: str = Form("")):
    if not key.strip():
        return settings_back(request, "general", err="Enter an API key.")
    try:
        secrets.set_api_key(key)
    except VNError:
        return settings_back(request, "general", err="Could not store the API key in the keyring.")
    return settings_back(request, "general", msg="API key stored.")


@app.post("/settings/key/clear")
def clear_key(request: Request):
    try:
        secrets.delete_api_key()
    except VNError:
        return settings_back(request, "general", err="Could not clear the API key.")
    return settings_back(request, "general", msg="API key cleared.")


@app.post("/settings/key/test")
def test_key(request: Request):
    try:
        key = secrets.get_api_key()
        if not key:
            return settings_back(request, "general", err="No API key is stored.")
        result = claude_cli.test_key(key)
        if result.ok and (result.structured or {}).get("ok") is True:
            return settings_back(request, "general", msg=f"API key works. Cost: ${result.cost_usd:.4f}.")
        error = (result.error or "The test did not return ok.").replace(key, "[key hidden]")
        return settings_back(request, "general", err=error)
    except VNError as exc:
        return settings_back(request, "general", err=str(exc).replace(key, "[key hidden]") if 'key' in locals() and key else "Key test failed.")


@app.post("/update-downloaders")
def start_update(request: Request):
    return spawn_run(request, [sys.executable, "-m", "rot2gold.cli", "update-downloaders", "--origin", "app"], "Update")


@app.get("/")
async def home(request: Request):
    return back("/ideas")


@app.post("/connections")
def add_connection(request: Request, platform: str = Form(...), url: str = Form(...), name: str = Form(""),
                   cookies_mode: str = Form("auto")):
    try:
        connections.add(db.connect(), platform, url, name, cookies_mode)
    except ValueError as exc:
        return back_to(request, err=str(exc))
    return back_to(request, msg="Collection added. Press Extract new videos to read it.")


@app.post("/connections/{cid}")
def edit_connection(request: Request, cid: int, name: str = Form(""), url: str = Form(""),
                    cookies_mode: str = Form("auto"), firefox_profile: str = Form(""), links: str = Form("")):
    con = db.connect()
    try:
        connections.update(con, cid, name=name, url=url, cookies_mode=cookies_mode, firefox_profile=firefox_profile)
        kept = connections.set_links(con, cid, links)
    except ValueError as exc:
        return back_to(request, err=str(exc))
    return back_to(request, msg="Collection saved." + (f" {kept} post URLs kept for when listing fails." if kept else ""))


@app.get("/connections/{cid}/delete", response_class=HTMLResponse)
async def confirm_delete(request: Request, cid: int):
    con = db.connect()
    try:
        conn = dict(connections.get(con, cid))
    except ValueError as exc:
        return back(err=str(exc))
    return back("/ideas", err=f"Open the {conn['name']} collection menu to delete it.")


@app.post("/connections/{cid}/delete")
def delete_connection(request: Request, cid: int):
    try:
        connections.delete(db.connect(), cid)
    except ValueError as exc:
        return back_to(request, err=str(exc))
    if request.headers.get("referer", "").split("?")[0].endswith("/runs"):
        return back("/ideas", msg="Collection removed. Its notes, ideas and media are still in your brain.")
    return back_to(request, drop=("conn",), msg="Collection removed. Its notes, ideas and media are still in your brain.")


@app.post("/extract")
def start_extract(request: Request, conn: list[int] = Form([]), max_notes: str = Form(""), write_notes: str = Form(""),
                  find_ideas: str = Form("")):
    if not conn:
        conn = [r["id"] for r in db.connect().execute("SELECT id FROM connections ORDER BY id")]
    if not conn:
        return back_to(request, err="Add a collection first: press + next to Collections.")
    cmd = [sys.executable, "-m", "rot2gold.cli", "extract", "--origin", "app", "--conn", ",".join(map(str, conn))]
    if max_notes.strip().isdigit():
        cmd += ["--max-notes", max_notes.strip()]
    if not write_notes:
        cmd.append("--no-notes")
    if not find_ideas:
        cmd.append("--no-ideas")
    return spawn_run(request, cmd, "Extract")


def spawn_run(request: Request, cmd: list[str], label: str):
    """Start an independent recorded run and wait for its lock record."""
    if info := lock.holder():
        return back_to(request, err=f"The pipeline is already running: {lock.describe(info)}.")
    LOGS.mkdir(parents=True, exist_ok=True)
    log = LOGS / f"{label.lower()}-{datetime.now():%Y%m%d-%H%M%S}.log"
    env = dict(os.environ)
    # The note-writing agent calls `r2g`: make sure it's on PATH even if the app was started from a launcher.
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
            finished = db.connect().execute("SELECT id FROM runs WHERE pid = ? ORDER BY id DESC LIMIT 1", (proc.pid,)).fetchone()
            if finished:
                return back(f"/runs/{finished['id']}")
            tail = log.read_text().strip().splitlines()[-3:]
            return back_to(request, err=f"{label} stopped right away: " + " ".join(tail))
        time.sleep(0.1)
    return back_to(request, msg=f"{label} is starting…")


@app.post("/runs/stop")
def stop_run(request: Request):
    info = lock.holder()
    if not info:
        return back_to(request, msg="Nothing is running.")
    try:
        # SIGINT is the polite "please stop" (like Ctrl+C): downloads stop after the current post,
        # claude ends its turn, and the run records what it finished.
        os.killpg(os.getpgid(info["pid"]), signal.SIGINT)
    except ProcessLookupError:
        return back_to(request, msg="The run had already ended.")
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


def thumbnails(con) -> dict[str, str]:
    """First available image for each post, in a single database read."""
    return {r["post_id"]: f"/media/{r['post_id']}/{Path(r['path']).name}" for r in con.execute(
        "SELECT i.post_id, i.path FROM images i WHERE i.idx = "
        "(SELECT MIN(j.idx) FROM images j WHERE j.post_id = i.post_id)")}


def source_lookup(con, wanted: set[str]) -> dict[str, dict]:
    if not wanted:
        return {}
    found = {}
    for row in con.execute("SELECT p.id, p.note_path, i.path AS image_path FROM posts p "
                           "LEFT JOIN images i ON i.post_id = p.id AND i.idx = "
                           "(SELECT MIN(j.idx) FROM images j WHERE j.post_id = p.id) "
                           "WHERE p.note_path IS NOT NULL"):
        name = Path(row["note_path"]).stem
        if name not in wanted:
            continue
        path = brain.note_file(row["note_path"])
        title = notefile.read(path, head_only=True).title if path.is_file() else name
        thumb = f"/media/{row['id']}/{Path(row['image_path']).name}" if row["image_path"] else None
        found[name] = {"name": name, "url": f"/videos/{row['id']}", "thumbnail": thumb, "title": title, "kind": "video"}
    for name, path in notefile.brain_names().items():
        if name in wanted:
            found.setdefault(name, {"name": name, "url": notefile.obsidian_link(path), "title": name, "kind": "note"})
    return found


def decorate_ideas(rows: list[dict], lookup: dict) -> list[dict]:
    for item in rows:
        item["source_tiles"] = [lookup.get(name, {"name": name, "title": name, "kind": "missing"}) for name in item["sources"]]
    return rows


VIDEO_GROUPS = {"waiting": ("new", "fetched", "processed"), "skipped": ("skipped",)}  # the rest are noted


@app.get("/videos", response_class=HTMLResponse)
async def videos(request: Request, conn: str = "", status: str = "", q: str = ""):
    con = db.connect()
    where, args = [], []
    if conn.isdigit():
        where.append("EXISTS (SELECT 1 FROM connection_posts x WHERE x.post_id = p.id AND x.connection_id = ?)")
        args.append(int(conn))
    sql = ("SELECT p.* FROM posts p" + (" WHERE " + " AND ".join(where) if where else "") +
           " ORDER BY COALESCE(p.upload_date, '') DESC, p.rowid DESC")
    matching = []
    needle = q.strip().lower()
    for r in con.execute(sql, args):
        item = dict(r) | note_head(r)
        if needle and needle not in " ".join(str(item.get(k) or "") for k in
                                             ("id", "creator", "title", "description", "skip_reason")).lower():
            continue
        matching.append(item)
    status = status if status in VIDEO_GROUPS else ""
    rows = [r for r in matching if not status or r["status"] in VIDEO_GROUPS[status]]
    thumbs = thumbnails(con)
    for item in rows:
        item["thumbnail"] = thumbs.get(item["id"])
    names = {r["id"]: r["name"] for r in con.execute("SELECT id, name FROM connections ORDER BY id")}
    current = {"conn": conn if conn.isdigit() and int(conn) in names else "", "status": status, "q": q.strip()}

    def link(**change):
        """This page's address with some filters changed; the others are kept."""
        params = {k: v for k, v in (current | change).items() if v}
        return "/videos" + ("?" + urlencode(params) if params else "")

    # Only the groups that have something in them get a chip: "All 111 · Skipped 3".
    counts = {g: sum(r["status"] in states for r in matching) for g, states in VIDEO_GROUPS.items()}
    chips = [{"label": "All", "href": link(status=""), "count": len(matching), "current": not status}] + [
        {"label": g.capitalize(), "href": link(status=g), "count": counts[g], "current": status == g}
        for g in VIDEO_GROUPS if counts[g] or status == g]
    conn_filter = {"name": names[int(current["conn"])], "clear": link(conn="")} if current["conn"] else None
    return page(request, "videos.html", rows=rows, chips=chips if len(chips) > 1 else [], conn_filter=conn_filter, f=current)


@app.get("/videos/{post_id}", response_class=HTMLResponse)
async def video(request: Request, post_id: str):
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
    stem = Path(post["note_path"]).stem if post["note_path"] else None
    related = {kind: [r for r in ideas.list_items(kind) if stem in r["sources"]] for kind in ideas.KINDS}
    return page(request, "video.html", post=post, images=images, segments=segments, conns=conns,
                note=note, note_html=note_html, obsidian=obsidian,
                related_ideas=related["idea"], related_learnings=related["learning"], related_events=related["event"])


@app.get("/media/{post_id}/{name}")
def media(post_id: str, name: str):
    """Frame and slide images, only from inside data/media/."""
    path = (media_dir(post_id) / name).resolve()
    if not path.is_relative_to(MEDIA.resolve()) or not path.is_file():
        return HTMLResponse("Not found", status_code=404)
    return FileResponse(path)


def idea_rows(con, folder=None, kinds=("idea",)):
    items = [item for kind in kinds for item in ideas.list_items(kind, folder)]
    wanted = {name for item in items for name in item["sources"]}
    lookup = source_lookup(con, wanted)
    return decorate_ideas([item | {"source_links": [{"name": name, "url": lookup.get(name, {}).get("url")} for name in item["sources"]],
                    "obsidian": notefile.obsidian_link(item["path"]) if folder is None else None}
            for item in items], lookup)


# What differs between the Ideas, Learnings and Events pages; all three use ideas.html.
KIND_PAGES = {
    "idea": {"kind": "idea", "base": "/ideas", "label": "Ideas", "one": "idea", "many": "ideas",
             "lede": "What your saved videos keep pointing to. New ones appear here after each Extract.",
             "empty": "No ideas yet. Press <strong>Extract new videos</strong> in the sidebar: ideas appear here once a few videos point the same way.",
             "status_hint": "To mark it as trying, kept or dropped, change <code>status</code> in Obsidian."},
    "learning": {"kind": "learning", "base": "/learnings", "label": "Learnings", "one": "learning", "many": "learnings",
                 "lede": "What your saved videos taught, combined across the videos that say the same thing.",
                 "empty": "No learnings yet. Press <strong>Extract new videos</strong> in the sidebar: each Extract also checks your notes for what they teach.",
                 "status_hint": "To mark it as kept or dropped, change <code>status</code> in Obsidian."},
    "event": {"kind": "event", "base": "/events", "label": "Events", "one": "event", "many": "events",
              "lede": "What your saved videos report or announce: things that happened, and things coming up.",
              "empty": "No events yet. Press <strong>Extract new videos</strong> in the sidebar: each Extract also checks your notes for events.",
              "status_hint": "To mark it as going, kept or dropped, change <code>status</code> in Obsidian."},
}
# Events are filtered by when they happen, not by status.
EVENT_GROUPS = {"upcoming": "Coming up", "past": "Past", "undated": "No date"}


def idea_view(request, name=None, status="all", q="", kind="idea"):
    con = db.connect()
    k = KIND_PAGES[kind]
    all_rows = idea_rows(con, kinds=(kind,))
    searched = [r for r in all_rows if not q.strip() or q.strip().lower() in
                " ".join(str(r[f]) for f in ("title", "description", "name")).lower()]
    if kind == "event":
        field, options = "timing", EVENT_GROUPS
    else:
        field, options = "status", {"new": "New", "trying": "Trying", "kept": "Kept", "dropped": "Dropped"}
    counts = {key: sum(r[field] == key for r in searched) for key in options}
    rows = [r for r in searched if status not in counts or r[field] == status]
    selected = next((r for r in all_rows if r["name"] == name), None) if name else (rows[0] if rows else None)
    if name and not selected:
        return back(k["base"], err=f"No {k['one']} named {name}. It may have been renamed or moved in Obsidian.")
    html = notefile.render(notefile.read(selected["path"]).body, note_links(con)) if selected else ""
    removal = delete.plan(con, selected["name"]) if selected else None  # for the Delete card
    column = ideas.CHECKS[kind][0]
    pending = {Path(r["note_path"]).stem for r in con.execute(
        f"SELECT note_path FROM posts WHERE status = 'done' AND note_path IS NOT NULL AND {column} IS NULL")}
    themes = [{"name": n, "total": len(names), "unchecked": len(set(names) & pending)} for n, names in ideas.themes().items()]
    # Ideas: only older notes under a theme need the button (new ones are checked by Extract).
    # Learnings and events: every unchecked note counts, since Extract works through them of any age.
    unchecked = len(pending & {name for names in ideas.themes().values() for name in names}) if kind == "idea" else len(pending)

    def query(**params):
        params = {key: v for key, v in params.items() if v and v != "all"}
        return "?" + urlencode(params) if params else ""

    # Only statuses that have items get a chip, so a new list shows just "All 28 · New 28".
    chips = [{"label": label, "href": k["base"] + query(status=key, q=q), "count": len(searched) if key == "all" else counts[key],
              "current": status == key or (key == "all" and status not in counts)}
             for key, label in {"all": "All", **options}.items()
             if key == "all" or counts[key] or status == key]
    calendar = selected and kind == "event" and ideas.calendar_file(selected) is not None
    return page(request, "ideas.html", k=k, rows=rows, selected=selected, html=html, removal=removal, themes=themes,
                unchecked=unchecked, chips=chips, keep=query(status=status, q=q), status=status if status in counts else "",
                q=q, detail_page=bool(name), groups=EVENT_GROUPS, calendar=calendar)


@app.get("/ideas", response_class=HTMLResponse)
async def idea_index(request: Request, status: str = "all", q: str = ""):
    return idea_view(request, status=status, q=q)


@app.get("/learnings", response_class=HTMLResponse)
async def learning_index(request: Request, status: str = "all", q: str = ""):
    return idea_view(request, status=status, q=q, kind="learning")


@app.get("/events", response_class=HTMLResponse)
async def event_index(request: Request, status: str = "all", q: str = ""):
    return idea_view(request, status=status, q=q, kind="event")


@app.post("/ideas/rebuild")
def start_ideas_rebuild(request: Request, themes: list[str] = Form([]), dry_run: str = Form(""), limit: str = Form("")):
    cmd = [sys.executable, "-m", "rot2gold.cli", "ideas", "rebuild", "--origin", "app"]
    if themes:
        cmd += ["--themes", ",".join(themes)]
    if dry_run:
        cmd.append("--dry-run")
    if limit.strip().isdigit():
        cmd += ["--limit", limit.strip()]
    return spawn_run(request, cmd, "Ideas")


@app.get("/ideas/preview/{run_id}", response_class=HTMLResponse)
async def idea_preview(request: Request, run_id: int):
    con = db.connect()
    run = con.execute("SELECT kind FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not run or run["kind"] != "ideas-dry-run":
        return HTMLResponse("Not found", status_code=404)
    root = (DATA / "ideas-dry-run").resolve()
    folder = (root / f"run-{run_id}").resolve()
    if not folder.is_relative_to(root):
        return HTMLResponse("Not found", status_code=404)
    rows = idea_rows(con, folder, kinds=tuple(ideas.KINDS)) if folder.is_dir() else []
    for item in rows:
        note = notefile.read(item["path"])
        item["html"] = notefile.render(note.body, note_links(con))
        item["is_update"] = (ideas.kind_dir(item["kind"]) / item["path"].name).is_file()
    rows.sort(key=lambda item: item["is_update"])  # new items first
    manifest = ideas.read_manifest(folder) if folder.is_dir() else {}
    checked = len({pid for _, key in ideas.CHECKS.values() for pid in manifest.get(key, [])})
    return page(request, "idea-preview.html", rows=rows, run_id=run_id, manifest=manifest, checked=checked)


@app.post("/ideas/preview/{run_id}/apply")
def apply_preview(run_id: int):
    """Quick (no AI): runs in the request, but still under the pipeline lock."""
    from ..runs import recorded_run
    done = None
    try:
        with recorded_run("app", "r2g ideas apply", "ideas", [], load()) as run:
            run.report.set_stage("ideas")
            done = ideas.apply_dry_run(run.con, run_id, run.report, run.run_id)
            run.counts.update(done["counts"])
            run.report.set_stage("done")
    except (ValueError, VNError) as exc:  # e.g. the lock is held: no run was recorded
        return back(f"/ideas/preview/{run_id}", err=str(exc))
    # recorded_run stores a failure in the run's history instead of raising it: check how it ended.
    if done is None:
        return back(f"/ideas/preview/{run_id}", err=run_failure(run))
    return back("/ideas", msg=f"Applied dry run {run_id}: {plural(len(done['copied']), 'note')} written to the brain"
                + (f", {len(done['skipped'])} skipped because you changed them since" if done["skipped"] else "")
                + (f" (commit {done['commit']})" if done["commit"] else "") + ".")


def delete_item(request: Request, name: str, with_videos: str):
    """Quick (no AI): runs in the request, under the pipeline lock, as a run Undo can revert."""
    from ..runs import recorded_run
    done = None
    try:
        title = delete.plan(db.connect(), name)["idea"]["title"]
        with recorded_run("app", f"r2g delete {name}", "delete", [], load()) as run:
            run.report.set_stage("delete")
            done = delete.delete_idea(run.con, name, bool(with_videos), run.report, run.run_id)
            run.counts["posts_skipped"] = len(done["videos"])  # History says how many videos went with it
            run.report.set_stage("done")
    except (ValueError, VNError) as exc:  # unknown idea, or the lock is held: nothing was deleted
        return back_to(request, err=str(exc))
    if done is None:
        return back_to(request, err=run_failure(run))
    videos = len(done["videos"])
    return back(KIND_PAGES[ideas.kind_of(name)]["base"],
                msg=f"Deleted “{title}”" + (f" and {videos} {'video' if videos == 1 else 'videos'}" if videos else "")
                + f". You can undo it from History.")


@app.post("/ideas/{name}/delete")
def delete_idea(request: Request, name: str, with_videos: str = Form("")):
    if ideas.kind_of(name) != "idea":
        return HTMLResponse("Not found", status_code=404)
    return delete_item(request, name, with_videos)


@app.post("/learnings/{name}/delete")
def delete_learning(request: Request, name: str, with_videos: str = Form("")):
    if ideas.kind_of(name) != "learning":
        return HTMLResponse("Not found", status_code=404)
    return delete_item(request, name, with_videos)


@app.get("/ideas/{name}", response_class=HTMLResponse)
async def idea_detail(request: Request, name: str, status: str = "all", q: str = ""):
    if not name.startswith("idea-") or Path(name).name != name:
        return HTMLResponse("Not found", status_code=404)
    return idea_view(request, name, status, q)


@app.get("/learnings/{name}", response_class=HTMLResponse)
async def learning_detail(request: Request, name: str, status: str = "all", q: str = ""):
    if not name.startswith("learning-") or Path(name).name != name:
        return HTMLResponse("Not found", status_code=404)
    return idea_view(request, name, status, q, kind="learning")


@app.post("/events/{name}/delete")
def delete_event(request: Request, name: str, with_videos: str = Form("")):
    if ideas.kind_of(name) != "event":
        return HTMLResponse("Not found", status_code=404)
    return delete_item(request, name, with_videos)


@app.get("/events/{name}/calendar.ics")
def event_calendar(name: str):
    """Add to calendar: an .ics file for an upcoming event with a full date."""
    item = next((e for e in ideas.list_events() if e["name"] == name), None) if ideas.kind_of(name) == "event" else None
    text = ideas.calendar_file(item) if item else None
    if not text:
        return HTMLResponse("Not found", status_code=404)
    return Response(text, media_type="text/calendar",
                    headers={"Content-Disposition": f'attachment; filename="{name.removeprefix("event-")}.ics"'})


@app.get("/events/{name}", response_class=HTMLResponse)
async def event_detail(request: Request, name: str, status: str = "all", q: str = ""):
    if not name.startswith("event-") or Path(name).name != name:
        return HTMLResponse("Not found", status_code=404)
    return idea_view(request, name, status, q, kind="event")


@app.get("/runs", response_class=HTMLResponse)
async def runs(request: Request, conn: str = "", kind: str = ""):
    con = db.connect()
    active = active_run(con)
    where, args = [], []
    if conn.isdigit():
        where.append("',' || connection_ids || ',' LIKE '%,' || ? || ',%'")
        args.append(conn)
    if kind == "ideas":
        where.append("kind LIKE 'ideas%'")
    names = {r["id"]: r["name"] for r in con.execute("SELECT id, name FROM connections")}
    rows = [deleted_kind(con, dict(r)) for r in con.execute(
        "SELECT * FROM runs" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id DESC LIMIT 50", args)]
    for r in rows:
        r["title"] = run_title(r, names)
    conn_name = names.get(int(conn)) if conn.isdigit() else None
    return page(request, "runs.html", runs=rows, active=active, conn_name=conn_name, kind=kind)


@app.get("/runs/{run_id}", response_class=HTMLResponse)
async def run_page(request: Request, run_id: int):
    con = db.connect()
    active = active_run(con)
    row = con.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not row:
        return back("/runs", err=f"No run {run_id}.")
    events = [dict(e) for e in con.execute("SELECT * FROM run_events WHERE run_id = ? ORDER BY id", (run_id,))]
    batches = [dict(b) for b in con.execute("SELECT * FROM batches WHERE run_id = ? ORDER BY id", (run_id,))]
    names = {r["id"]: r["name"] for r in con.execute("SELECT id, name FROM connections")}
    stages = (["sync", "fetch", "process", "notes", "ideas", "done"] if row["kind"] == "extract" else
              ["undo", "done"] if row["kind"] == "undo" else ["delete", "done"] if row["kind"] == "delete" else ["update", "done"] if row["kind"] == "update" else
              ["ideas", "done"])
    preview = None
    if row["kind"] == "ideas-dry-run" and (folder := ideas.dry_run_dir(run_id)).is_dir():
        preview = {"applied": ideas.read_manifest(folder).get("applied"), "count": len(ideas.note_files(folder))}
    run = deleted_kind(con, dict(row))
    return page(request, "run.html", run=run, title=run_title(run, names), events=events, batches=batches,
                stages=stages, names=names, active=active, preview=preview, last_event=events[-1]["id"] if events else 0)


@app.get("/runs/{run_id}/undo", response_class=HTMLResponse)
async def confirm_undo(request: Request, run_id: int):
    row = db.connect().execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if not row or row["status"] == "running" or row["undone_at"] or not row["brain_commits"]:
        return back("/runs", err="This run cannot be undone.")
    return page(request, "undo.html", run=dict(row), commits=row["brain_commits"].split())


@app.post("/runs/{run_id}/undo")
def perform_undo(run_id: int):
    from ..runs import recorded_run
    undone = False
    try:
        with recorded_run("app", f"r2g undo {run_id}", "undo", [], load()) as run:
            run.report.set_stage("undo")
            undo.undo_run(run.con, run_id, run.report)
            undone = True
            run.report.set_stage("done")
    except (ValueError, VNError) as exc:  # e.g. the lock is held: no run was recorded
        return back(f"/runs/{run_id}", err=str(exc))
    # recorded_run stores a failure in the run's history instead of raising it: check how it ended.
    if not undone:
        return back(f"/runs/{run_id}", err=run_failure(run))
    return back(f"/runs/{run.run_id}", msg=f"Run {run_id} was undone.")


def run_failure(run) -> str:
    """The error a recorded run ended with, without the hint line meant for the terminal."""
    error = (run.row().get("error") or "It failed; see the run log.").split("\n")[0]
    return error.replace("ValueError: ", "")


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


@app.post("/quit", response_class=HTMLResponse)
def quit_app(request: Request):
    if server is not None:
        threading.Timer(0.3, lambda: setattr(server, "should_exit", True)).start()
    return templates.TemplateResponse(request, "stopped.html", {"running": lock.holder() is not None})


def serve(open_browser: bool = True) -> None:
    import uvicorn
    global server
    port = int(load()["app"]["port"])
    url = f"http://{HOST}:{port}"
    with socket.socket() as sock:
        if sock.connect_ex((HOST, port)) == 0:
            try:
                with urllib.request.urlopen(url + "/healthz", timeout=2) as response:
                    if json.load(response).get("app") == APP_NAME:
                        print(f"{APP_NAME} is already running at {url}")
                        if open_browser:
                            webbrowser.open(url)
                        return
            except Exception:
                pass
            raise VNError(f"Port {port} is already in use by another app.")
    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=port, log_level="warning"))
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    if not sys.stdin.isatty():
        LOGS.mkdir(parents=True, exist_ok=True)
        with open(LOGS / "ui.log", "a") as log, redirect_stdout(log), redirect_stderr(log):
            print(f"{APP_NAME} at {url}", flush=True)
            server.run()
    else:
        print(f"{APP_NAME} at {url}  (Ctrl+C to stop the server; a running Extract keeps going)")
        server.run()
