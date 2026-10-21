"""Show downloader freshness and upgrade both tools in the environment the app runs in."""

import json
import shutil
import subprocess
import sys
from datetime import date
from importlib import metadata
from pathlib import Path

from .errors import ToolMissing, VNError


def versions() -> dict:
    def version(name):
        try:
            return metadata.version(name)
        except metadata.PackageNotFoundError:
            return None
    yt, gallery = version("yt-dlp"), version("gallery-dl")
    try:
        age = (date.today() - date(*map(int, yt.split(".")[:3]))).days if yt else None  # "2026.8.19": no zero padding
    except ValueError:
        age = None
    return {"yt-dlp": yt, "gallery-dl": gallery, "yt-dlp_age_days": age}


def update(report) -> dict:
    uv = shutil.which("uv") or str(Path.home() / ".local/bin/uv")
    if not Path(uv).is_file():
        raise ToolMissing("uv not found", "Install uv (docs.astral.sh/uv) before updating downloaders.")
    report(f"Before: {versions()}")
    cmd = [uv, "pip", "install", "--python", sys.executable, "-U",
           "yt-dlp[default,curl-cffi]", "gallery-dl"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
        report(line.rstrip())
    if proc.wait() != 0:
        raise VNError(f"Downloader update failed (exit {proc.returncode}).")
    code = ("import json; from importlib.metadata import version, PackageNotFoundError; "
            "print(json.dumps({n: version(n) for n in ('yt-dlp', 'gallery-dl')}))")
    after = json.loads(subprocess.run([sys.executable, "-c", code],
                                      capture_output=True, text=True, check=True).stdout)
    report(f"After: {after}")
    return after
