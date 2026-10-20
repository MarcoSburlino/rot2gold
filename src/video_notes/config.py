"""Project paths and defaults, with user preferences overlaid outside Git."""

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
    "ideas": {"since": "2026-10-19", "batch_size": 25, "model": "opus", "max_new_per_pass": 5,
              "max_new_learnings_per_pass": 8, "max_new_events_per_pass": 8},
    "app": {"port": 8740},
}


def load() -> dict:
    with open(ROOT / "config.toml", "rb") as f:
        cfg = tomllib.load(f)
    for section, values in DEFAULTS.items():
        cfg[section] = values | cfg.get(section, {})
    from .settings import EDITABLE, read
    saved = read()
    for field in EDITABLE:
        section, key = field["section"], field["key"]
        if isinstance(saved.get(section), dict) and key in saved[section]:
            cfg.setdefault(section, {})[key] = saved[section][key]
    return cfg


def brain_dir(cfg: dict | None = None) -> Path:
    return Path((cfg or load())["brain"]["path"]).expanduser()


def media_dir(post_id: str) -> Path:
    return MEDIA / post_id.replace(":", "_")
