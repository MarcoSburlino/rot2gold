"""Firefox profiles, for reading cookies when a platform needs a login."""

import configparser
import os
from pathlib import Path

# Linux: Firefox 147+ follows the XDG layout; older installs and Flatpak use other folders. Then macOS and Windows.
ROOTS = ["~/.config/mozilla/firefox", "~/.mozilla/firefox", "~/.var/app/org.mozilla.firefox/config/mozilla/firefox",
         "~/.var/app/org.mozilla.firefox/.mozilla/firefox", "~/Library/Application Support/Firefox",
         os.path.join(os.environ.get("APPDATA", "~/AppData/Roaming"), "Mozilla", "Firefox")]


def profiles() -> list[dict]:
    """[{name, path, default}] from every profiles.ini found."""
    found = []
    for root in (Path(r).expanduser() for r in ROOTS):
        ini = root / "profiles.ini"
        if not ini.exists():
            continue
        cp = configparser.ConfigParser()
        cp.read(ini)
        install_default = next((cp[s].get("Default") for s in cp.sections() if s.startswith("Install")), None)
        for s in cp.sections():
            if not s.startswith("Profile"):
                continue
            p = cp[s]
            path = root / p["Path"] if p.get("IsRelative", "1") == "1" else Path(p["Path"])
            found.append({"name": p.get("Name", path.name), "path": str(path),
                          "default": p.get("Path") == install_default or p.get("Default") == "1",
                          "has_cookies": (path / "cookies.sqlite").exists()})
    return found
