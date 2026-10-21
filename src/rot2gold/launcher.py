"""Add the app to the system's app menu, so it opens like any other app.

Linux: a .desktop entry and its icon. macOS: a small Rot2Gold.app in ~/Applications that runs `r2g ui`.
Windows: a Start menu shortcut, made with PowerShell.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .web.app import APP_NAME, HERE

ICON = HERE / "static/icon.png"


def r2g_command() -> str:
    """The installed `r2g` program: the one on PATH, or the one next to this Python."""
    return shutil.which("r2g") or str(Path(sys.executable).parent / ("r2g.exe" if os.name == "nt" else "r2g"))


def install(home: Path | None = None) -> tuple[Path, Path]:
    """Returns (the launcher, its icon)."""
    home = home or Path.home()
    if sys.platform == "darwin":
        return _install_mac(home)
    if os.name == "nt":
        return _install_windows(home)
    return _install_linux(home)


def uninstall(home: Path | None = None) -> None:
    home = home or Path.home()
    for path in _linux_paths(home) + [_mac_app(home), *_windows_paths(home)]:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)


def _linux_paths(home: Path) -> list[Path]:
    icons = home / ".local/share/icons/hicolor"
    # The icon was an SVG, then a 256 px PNG, before the 512 px R2G icon (2026-10-21); the last two are removed.
    return [home / ".local/share/applications/rot2gold.desktop", icons / "512x512/apps/rot2gold.png",
            icons / "256x256/apps/rot2gold.png", icons / "scalable/apps/rot2gold.svg"]


def _install_linux(home: Path) -> tuple[Path, Path]:
    desktop, icon, *old_icons = _linux_paths(home)
    for folder in (desktop.parent, icon.parent):
        folder.mkdir(parents=True, exist_ok=True)
    # Written next to the old file and swapped in, so the desktop never reads a half-copied icon and caches it as broken.
    partial = icon.with_suffix(".partial")
    shutil.copyfile(ICON, partial)
    os.replace(partial, icon)
    for old in old_icons:
        old.unlink(missing_ok=True)
    # By name, not by path: the desktop then finds it through the icon theme, which notices when it changes.
    desktop.write_text(f"[Desktop Entry]\nType=Application\nName={APP_NAME}\n"
                       f"Comment=Turn saved posts into notes and ideas\nExec=\"{r2g_command()}\" ui\n"
                       f"Icon={icon.stem}\nTerminal=false\nCategories=Utility;\n")
    if exe := shutil.which("update-desktop-database"):
        subprocess.run([exe, str(desktop.parent)], capture_output=True)
    return desktop, icon


def _mac_app(home: Path) -> Path:
    return home / "Applications" / f"{APP_NAME}.app"


def _install_mac(home: Path) -> tuple[Path, Path]:
    from PIL import Image
    app = _mac_app(home)
    (app / "Contents/MacOS").mkdir(parents=True, exist_ok=True)
    (app / "Contents/Resources").mkdir(parents=True, exist_ok=True)
    icon = app / "Contents/Resources/icon.icns"
    Image.open(ICON).save(icon)
    script = app / "Contents/MacOS" / APP_NAME
    script.write_text(f"#!/bin/sh\nexec \"{r2g_command()}\" ui\n")
    script.chmod(0o755)
    (app / "Contents/Info.plist").write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>{APP_NAME}</string>
  <key>CFBundleIdentifier</key><string>io.github.rot2gold</string>
  <key>CFBundleExecutable</key><string>{APP_NAME}</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
</dict></plist>
""")
    return app, icon


def _windows_paths(home: Path) -> list[Path]:
    start_menu = Path(os.environ.get("APPDATA", home / "AppData/Roaming")) / "Microsoft/Windows/Start Menu/Programs"
    return [start_menu / f"{APP_NAME}.lnk", Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local")) / "rot2gold/icon.ico"]


def _install_windows(home: Path) -> tuple[Path, Path]:
    from PIL import Image
    shortcut, icon = _windows_paths(home)
    icon.parent.mkdir(parents=True, exist_ok=True)
    Image.open(ICON).save(icon, sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
    # WindowStyle 7: start minimised, so the server's console window stays out of the way.
    script = (f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{shortcut}'); "
              f"$s.TargetPath = '{r2g_command()}'; $s.Arguments = 'ui'; $s.IconLocation = '{icon}'; "
              f"$s.WindowStyle = 7; $s.Description = 'Turn saved posts into notes and ideas'; $s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True, capture_output=True)
    return shortcut, icon
