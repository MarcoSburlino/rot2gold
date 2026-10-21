"""Settings: the bundled defaults, overlaid by the user's config.toml (written by setup and Settings)."""

import os
import tempfile
import tomllib
from pathlib import Path

import tomli_w

from .paths import CHECKOUT, RESOURCES, config_file, default_data_dir

ROOT = CHECKOUT
PROMPTS = ROOT / "prompts"
# Vault paths the app writes, relative to the vault (see [vault] in defaults.toml).
VAULT_KEYS = ("videos", "hub", "quotes", "ideas", "learnings", "events", "templates")


class ConfigError(Exception):
    pass


def defaults() -> dict:
    with open(RESOURCES / "defaults.toml", "rb") as f:
        return tomllib.load(f)


def read_user() -> dict:
    """The user's own config.toml, or {} before setup."""
    path = config_file()
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from None


def write_user(values: dict) -> None:
    """Replace the user's config.toml in one step, so a crash never leaves half a file."""
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix="config-", suffix=".tmp", delete=False,
                                         encoding="utf-8") as f:
            name = f.name
            f.write(tomli_w.dumps(values))
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def load() -> dict:
    cfg = defaults()
    for section, values in read_user().items():
        if isinstance(values, dict) and isinstance(cfg.get(section), dict):
            cfg[section] = cfg[section] | values
        else:
            cfg[section] = values
    return cfg


def is_set_up(cfg: dict | None = None) -> bool:
    return bool((cfg or load())["vault"]["path"])


def data_dir(cfg: dict | None = None) -> Path:
    value = (cfg or load())["storage"]["data_dir"]
    return Path(value).expanduser() if value else default_data_dir()


def brain_dir(cfg: dict | None = None) -> Path:
    """The Obsidian vault."""
    return Path((cfg or load())["vault"]["path"]).expanduser()


def vault_rel(key: str, cfg: dict | None = None) -> str:
    """A [vault] path relative to the vault, with forward slashes: 'Rot2Gold/Videos'."""
    return str((cfg or load())["vault"][key]).strip("/").replace("\\", "/")


DATA = data_dir()
MEDIA = DATA / "media"
DB_PATH = DATA / "r2g.sqlite"
LINKS = DATA / "links.txt"  # v1 fallback list of post URLs; imported into the first connection
LOGS = DATA / "logs"


def media_dir(post_id: str) -> Path:
    return MEDIA / post_id.replace(":", "_")
