"""vn fetch: download media.

Video: download at a modest resolution, keep the frame at 0.5 s and 16 kHz mono audio, delete the video.
Slideshow: download every image in order with gallery-dl (no audio).
"""

import random
import shutil
import subprocess
import sys
import time

import yt_dlp

from . import db
from .config import ROOT, load, media_dir
from .sync import is_slideshow, post_info, short, ydl_opts

MAX_ATTEMPTS = 3          # a post that fails this often is skipped with the error as reason
MAX_CONSECUTIVE_FAILS = 5  # this many in a row looks like a block: stop the run


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed: {(proc.stderr or proc.stdout).strip().splitlines()[-1:]}")


def fetch_video(con, post, cfg, cookies: bool) -> None:
    out = media_dir(post["id"])
    out.mkdir(parents=True, exist_ok=True)
    opts = ydl_opts(
        cookies,
        format="b/bv*+ba",
        format_sort=[f"res:{cfg['fetch']['max_resolution']}"],
        outtmpl=str(out / "video.%(ext)s"),
    )
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(post["url"], download=True)
        video = ydl.prepare_filename(info)
    frame, audio = out / "frame.png", out / "audio.wav"
    run(["ffmpeg", "-y", "-v", "error", "-ss", "0.5", "-i", video, "-frames:v", "1", str(frame)])
    has_audio = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", video],
        capture_output=True, text=True,
    ).stdout.strip()
    if has_audio:
        run(["ffmpeg", "-y", "-v", "error", "-i", video, "-vn", "-ac", "1", "-ar", "16000", str(audio)])
    (out / video.rsplit("/", 1)[-1]).unlink(missing_ok=True)
    con.execute("DELETE FROM images WHERE post_id = ?", (post["id"],))
    con.execute(
        "INSERT INTO images (post_id, idx, kind, path) VALUES (?, 0, 'frame', ?)",
        (post["id"], str(frame.relative_to(ROOT))),
    )


def fetch_slideshow(con, post, cookies: bool) -> None:
    out = media_dir(post["id"])
    if out.exists():
        shutil.rmtree(out)  # start clean so slide numbering can't mix with a partial earlier run
    out.mkdir(parents=True)
    cmd = [sys.executable, "-m", "gallery_dl", "-q", "-D", str(out), "-f", "slide-{num:>02}.{extension}",
           "--filter", "extension not in ('mp3', 'm4a', 'mp4')", "--no-mtime"]
    if cookies:
        cmd += ["--cookies-from-browser", "firefox"]
    run(cmd + [post["url"]])
    slides = sorted(p for p in out.iterdir() if p.name.startswith("slide-"))
    if not slides:
        raise RuntimeError("gallery-dl downloaded no images")
    con.execute("DELETE FROM images WHERE post_id = ?", (post["id"],))
    for i, p in enumerate(slides, start=1):
        con.execute(
            "INSERT INTO images (post_id, idx, kind, path) VALUES (?, ?, 'slide', ?)",
            (post["id"], i, str(p.relative_to(ROOT))),
        )


def fetch(limit: int | None) -> int:
    cfg = load()
    con = db.connect()
    cookies = (con.execute("SELECT value FROM meta WHERE key = 'cookies'").fetchone() or ["0"])[0] == "1"
    posts = con.execute("SELECT * FROM posts WHERE status = 'new' ORDER BY rowid LIMIT ?", (limit or -1,)).fetchall()
    fails = done = 0
    for i, post in enumerate(posts):
        if i:
            time.sleep(random.uniform(cfg["fetch"]["delay_min"], cfg["fetch"]["delay_max"]))
        try:
            kind = post["type"]
            if kind is None:  # sync couldn't read its metadata: try again now
                kind = "slideshow" if is_slideshow(post_info(post["url"], cookies)) else "video"
                con.execute("UPDATE posts SET type = ? WHERE id = ?", (kind, post["id"]))
            if kind == "slideshow":
                fetch_slideshow(con, post, cookies)
            else:
                fetch_video(con, post, cfg, cookies)
            db.set_status(con, post["id"], "fetched", type=kind, last_error=None)
            print(f"fetched {post['id']} ({kind})")
            done += 1
            fails = 0
        except Exception as exc:
            con.rollback()
            attempts = post["fetch_attempts"] + 1
            err = short(exc)
            if attempts >= MAX_ATTEMPTS:
                db.set_status(con, post["id"], "skipped", skip_reason=f"fetch failed: {err}",
                              fetch_attempts=attempts, last_error=err)
                print(f"skipped {post['id']}: fetch failed {attempts} times: {err}")
            else:
                db.set_status(con, post["id"], "new", fetch_attempts=attempts, last_error=err)
                print(f"failed {post['id']} (attempt {attempts}): {err}")
            fails += 1
            if fails >= MAX_CONSECUTIVE_FAILS:
                raise SystemExit(f"{fails} downloads failed in a row; TikTok may be blocking. "
                                 "Try: uv pip install --python .venv/bin/python -U 'yt-dlp[default,curl-cffi]' gallery-dl")
    return done
