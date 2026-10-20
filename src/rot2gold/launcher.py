"""Install a small desktop entry so the local UI opens from GNOME."""

import shutil
import subprocess
from pathlib import Path

from .web.app import APP_NAME, HERE


def install(applications: Path | None = None, icons: Path | None = None, home: Path | None = None) -> tuple[Path, Path]:
    home = home or Path.home()
    applications = applications or home / ".local/share/applications"
    icons = icons or home / ".local/share/icons/hicolor/scalable/apps"
    applications.mkdir(parents=True, exist_ok=True)
    icons.mkdir(parents=True, exist_ok=True)
    icon = icons / "rot2gold.svg"
    desktop = applications / "rot2gold.desktop"
    shutil.copyfile(HERE / "static/icon.svg", icon)
    desktop.write_text(f"[Desktop Entry]\nType=Application\nName={APP_NAME}\n"
                       f"Comment=Turn saved posts into notes and ideas\nExec={home}/.local/bin/r2g ui\n"
                       f"Icon={icon}\nTerminal=false\nCategories=Utility;\n")
    if exe := shutil.which("update-desktop-database"):
        subprocess.run([exe, str(applications)], capture_output=True)
    return desktop, icon


def uninstall(applications: Path | None = None, icons: Path | None = None, home: Path | None = None) -> None:
    home = home or Path.home()
    (applications or home / ".local/share/applications").joinpath("rot2gold.desktop").unlink(missing_ok=True)
    (icons or home / ".local/share/icons/hicolor/scalable/apps").joinpath("rot2gold.svg").unlink(missing_ok=True)
