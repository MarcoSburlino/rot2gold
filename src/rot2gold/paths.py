"""Where the app keeps its config, its data and its bundled files, on Linux, macOS and Windows."""

import os
from pathlib import Path

import platformdirs

APP = "rot2gold"
PACKAGE = Path(__file__).resolve().parent
RESOURCES = PACKAGE / "resources"
CHECKOUT = PACKAGE.parents[1]  # the repository folder, when running from a Git clone


def config_file() -> Path:
    """The user's config.toml. R2G_CONFIG points somewhere else (tests, a second profile)."""
    if os.environ.get("R2G_CONFIG"):
        return Path(os.environ["R2G_CONFIG"]).expanduser()
    return platformdirs.user_config_path(APP, appauthor=False, roaming=True) / "config.toml"


def default_data_dir() -> Path:
    return platformdirs.user_data_path(APP, appauthor=False)
