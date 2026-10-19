"""Project paths and config.toml."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
MEDIA = DATA / "media"
DB_PATH = DATA / "vn.sqlite"
LINKS = DATA / "links.txt"  # v1 fallback list of post URLs; imported into the first connection
LOGS = DATA / "logs"
TOOLS = DATA / "tools"  # fallback tesseract unpacked from Fedora RPMs (see docs/spec.md)
PROMPTS = ROOT / "prompts"

DEFAULTS = {
    "brain": {"path": "~/Projects/brain"},
    "notes": {"backend": "subscription", "model": "opus", "batch_size": 5, "max_per_run": 20,
              "stop_at_plan_usage": 0.9},
    "app": {"port": 8740},
}


def load() -> dict:
    with open(ROOT / "config.toml", "rb") as f:
        cfg = tomllib.load(f)
    for section, values in DEFAULTS.items():
        cfg[section] = values | cfg.get(section, {})
    return cfg


def brain_dir(cfg: dict | None = None) -> Path:
    return Path((cfg or load())["brain"]["path"]).expanduser()


def media_dir(post_id: str) -> Path:
    return MEDIA / post_id.replace(":", "_")
