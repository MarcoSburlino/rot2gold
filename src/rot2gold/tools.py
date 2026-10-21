"""External programs the pipeline uses, found on Linux, macOS and Windows: Tesseract (OCR) and ffmpeg.

ffmpeg is always available: when it isn't installed, the copy bundled with the imageio-ffmpeg package is used.
Tesseract can't be bundled; without it, text on screen is not read (the AI can still look at the images).
"""

import os
import platform
import shutil
import subprocess
from pathlib import Path

# Where installers put Tesseract when it isn't on PATH.
TESSERACT_PLACES = {"Windows": [r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"],
                    "Darwin": ["/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract"]}


def tesseract(cfg: dict) -> str | None:
    """[ocr] tesseract if set, else the one on PATH, else a usual install place; None if there is none."""
    configured = (cfg.get("ocr") or {}).get("tesseract") or ""
    if configured:
        path = Path(configured).expanduser()
        return str(path) if path.is_file() else None
    if found := shutil.which("tesseract"):
        return found
    return next((p for p in TESSERACT_PLACES.get(platform.system(), []) if Path(p).is_file()), None)


def tesseract_langs(exe: str, tessdata: str = "") -> list[str]:
    """The language packs Tesseract has, e.g. ['eng', 'ita']."""
    env = dict(os.environ) | ({"TESSDATA_PREFIX": str(Path(tessdata).expanduser())} if tessdata else {})
    try:
        out = subprocess.run([exe, "--list-langs"], capture_output=True, text=True, timeout=20, env=env).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return sorted(line.strip() for line in out.splitlines()[1:] if line.strip() and line.strip() != "osd")


def install_hint(tool: str) -> str:
    """The command that installs `tool` on this system."""
    system = platform.system()
    if tool == "tesseract":
        if system == "Darwin":
            return "brew install tesseract tesseract-lang"
        if system == "Windows":
            return "winget install UB-Mannheim.TesseractOCR"
        for manager, cmd in (("dnf", "sudo dnf install tesseract (add tesseract-langpack-ita and so on for other languages)"),
                             ("apt", "sudo apt install tesseract-ocr (add tesseract-ocr-ita and so on for other languages)"),
                             ("pacman", "sudo pacman -S tesseract tesseract-data-eng"),
                             ("zypper", "sudo zypper install tesseract-ocr")):
            if shutil.which(manager):
                return cmd
        return "Install Tesseract OCR with your package manager."
    return f"Install {tool}."


def ffmpeg() -> str:
    if found := shutil.which("ffmpeg"):
        return found
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()
