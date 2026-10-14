"""Project paths and config.toml."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
MEDIA = DATA / "media"
DB_PATH = DATA / "vn.sqlite"
LINKS = DATA / "links.txt"
TOOLS = DATA / "tools"  # fallback tesseract unpacked from Fedora RPMs (see docs/spec.md)


def load() -> dict:
    with open(ROOT / "config.toml", "rb") as f:
        return tomllib.load(f)


def media_dir(post_id: str) -> Path:
    return MEDIA / post_id
