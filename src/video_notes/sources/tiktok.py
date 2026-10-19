"""TikTok collections: list with yt-dlp, download videos with yt-dlp + ffmpeg, slideshows with gallery-dl.

Only id, URL, creator, upload date and type are read: never captions, hashtags or comments.
"""

import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yt_dlp

from .base import Access, ListedPost, Source

URL_RE = re.compile(r"tiktok\.com/@([^/?#]+)/(?:video|photo)/(\d+)")
COLLECTION_RE = re.compile(r"^https?://(?:www\.)?tiktok\.com/@[^/?#]+/collection/[^/?#]+-(\d+)")


def ydl_opts(access: Access, **extra) -> dict:
    opts = {"quiet": True, "no_warnings": True, "noprogress": True}
    if access.cookies:
        opts["cookiesfrombrowser"] = ("firefox", access.firefox_profile) if access.firefox_profile else ("firefox",)
    opts.update(extra)
    return opts


def to_date(ts) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%d")


def is_slideshow(info: dict) -> bool:
    # TikTok photo posts expose only their background audio as a format.
    formats = info.get("formats") or []
    return bool(formats) and all((f.get("vcodec") in (None, "none")) for f in formats)


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"{Path(cmd[0]).name} failed: {(proc.stderr or proc.stdout).strip().splitlines()[-1:]}")


class TikTokSource(Source):
    platform = "tiktok"
    label = "TikTok collection"
    url_hint = "https://www.tiktok.com/@you/collection/Name-1234567890"

    def validate_url(self, url: str) -> str:
        url = url.strip()
        m = COLLECTION_RE.match(url)
        if not m:
            raise ValueError("Paste the collection's link, like " + self.url_hint)
        return m.group(0)  # drops ?is_from_webapp=… and other tracking parameters

    def default_name(self, url: str) -> str:
        tail = url.rstrip("/").split("/collection/")[-1]
        return tail.rsplit("-", 1)[0]

    def list_posts(self, url: str, access: Access) -> list[ListedPost]:
        with yt_dlp.YoutubeDL(ydl_opts(access, extract_flat="in_playlist")) as ydl:
            info = ydl.extract_info(url, download=False)
        posts = []
        for e in info.get("entries") or []:
            if not e or not e.get("id"):
                continue
            m = URL_RE.search(e.get("url") or "")
            posts.append(ListedPost(e["id"], e.get("url") or e.get("webpage_url"),
                                    e.get("uploader") or (m.group(1) if m else None), to_date(e.get("timestamp"))))
        if not posts:
            raise RuntimeError("yt-dlp returned an empty collection")
        return posts

    def parse_post_url(self, line: str) -> ListedPost | None:
        m = URL_RE.search(line)
        return ListedPost(m.group(2), line.strip(), m.group(1)) if m else None

    def post_info(self, url: str, access: Access) -> dict:
        """Full metadata for one post (no download)."""
        with yt_dlp.YoutubeDL(ydl_opts(access)) as ydl:
            return ydl.extract_info(url, download=False)

    def detect_type(self, post_url: str, access: Access) -> tuple[str, dict]:
        info = self.post_info(post_url, access)
        return ("slideshow" if is_slideshow(info) else "video",
                {"creator": info.get("uploader"), "upload_date": to_date(info.get("timestamp"))})

    def fetch(self, post_id, post_url, kind, out, cfg, access):
        return (self.fetch_slideshow(post_url, out, access) if kind == "slideshow"
                else self.fetch_video(post_url, out, cfg, access))

    def fetch_video(self, url: str, out: Path, cfg: dict, access: Access) -> list[tuple[str, Path]]:
        """Keep the frame at 0.5 s and 16 kHz mono audio; delete the video."""
        out.mkdir(parents=True, exist_ok=True)
        opts = ydl_opts(access, format="b/bv*+ba", format_sort=[f"res:{cfg['fetch']['max_resolution']}"],
                        outtmpl=str(out / "video.%(ext)s"))
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video = ydl.prepare_filename(info)
        frame, audio = out / "frame.png", out / "audio.wav"
        run(["ffmpeg", "-y", "-v", "error", "-ss", "0.5", "-i", video, "-frames:v", "1", str(frame)])
        has_audio = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", video],
            capture_output=True, text=True,
        ).stdout.strip()
        if has_audio:
            run(["ffmpeg", "-y", "-v", "error", "-i", video, "-vn", "-ac", "1", "-ar", "16000", str(audio)])
        Path(video).unlink(missing_ok=True)
        return [("frame", frame)]

    def fetch_slideshow(self, url: str, out: Path, access: Access) -> list[tuple[str, Path]]:
        """Every image in post order, with gallery-dl; the background audio is skipped."""
        if out.exists():
            for p in out.iterdir():  # start clean so slide numbering can't mix with a partial earlier run
                p.unlink()
        out.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, "-m", "gallery_dl", "-q", "-D", str(out), "-f", "slide-{num:>02}.{extension}",
               "--filter", "extension not in ('mp3', 'm4a', 'mp4')", "--no-mtime"]
        if access.cookies:
            cmd += ["--cookies-from-browser", "firefox" + (f":{access.firefox_profile}" if access.firefox_profile else "")]
        run(cmd + [url])
        slides = sorted(p for p in out.iterdir() if p.name.startswith("slide-"))
        if not slides:
            raise RuntimeError("gallery-dl downloaded no images")
        return [("slide", p) for p in slides]
