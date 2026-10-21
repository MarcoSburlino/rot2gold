"""First-run setup: what the setup page and `r2g setup` find, check and save.

Setup asks for the Obsidian vault, a folder name inside it, where to keep videos and other content,
the AI provider, the note language, the OCR languages and, optionally, a first collection.
Running it again keeps a custom vault layout unless the folder name is changed on purpose.
"""

import os
import platform
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

from . import ai, config, connections, db, secrets, sources, tools, vault
from .ai import codex_cli, gemini_cli, local
from .paths import default_data_dir

# Where Obsidian keeps its list of vaults: Linux (native, Flatpak, Snap), macOS, Windows.
OBSIDIAN_CONFIGS = ["~/.config/obsidian/obsidian.json", "~/.var/app/md.obsidian.Obsidian/config/obsidian/obsidian.json",
                    "~/snap/obsidian/current/.config/obsidian/obsidian.json",
                    "~/Library/Application Support/obsidian/obsidian.json",
                    os.path.join(os.environ.get("APPDATA", "~/AppData/Roaming"), "obsidian", "obsidian.json")]
SUBFOLDERS = {"videos": "Videos", "ideas": "Ideas", "learnings": "Learnings", "events": "Events", "templates": "Templates"}
LANGUAGES = {"eng": "English", "ita": "Italian", "spa": "Spanish", "fra": "French", "deu": "German", "por": "Portuguese",
             "nld": "Dutch", "pol": "Polish", "rus": "Russian", "ukr": "Ukrainian", "tur": "Turkish", "ara": "Arabic",
             "hin": "Hindi", "jpn": "Japanese", "kor": "Korean", "chi_sim": "Chinese (simplified)",
             "chi_tra": "Chinese (traditional)", "swe": "Swedish", "dan": "Danish", "nor": "Norwegian", "fin": "Finnish",
             "ces": "Czech", "ron": "Romanian", "ell": "Greek", "heb": "Hebrew", "ind": "Indonesian", "vie": "Vietnamese"}


def obsidian_vaults() -> list[dict]:
    """The vaults Obsidian knows about, most recently opened first: [{path, name, open}]."""
    import json
    found = {}
    for place in OBSIDIAN_CONFIGS:
        path = Path(place).expanduser()
        try:
            vaults = json.loads(path.read_text()).get("vaults", {})
        except (OSError, ValueError, AttributeError):
            continue
        for v in sorted(vaults.values(), key=lambda v: -(v.get("ts") or 0)):
            folder = Path(v.get("path") or "")
            if folder.is_dir() and str(folder) not in found:
                found[str(folder)] = {"path": str(folder), "name": folder.name, "open": bool(v.get("open"))}
    return list(found.values())


def layout(folder: str) -> dict:
    """The [vault] paths for a single app folder named `folder`."""
    folder = folder.strip().strip("/\\") or "Rot2Gold"
    return {key: f"{folder}/{sub}" for key, sub in SUBFOLDERS.items()} | {
        "hub": f"{folder}/{folder}.md", "quotes": f"{folder}/Quotes.md"}


def current_folder(cfg: dict) -> str:
    """The folder name if the vault uses the single-folder layout, else "" (a custom layout)."""
    head = config.vault_rel("videos", cfg).split("/")[0]
    return head if all(cfg["vault"].get(k) == v for k, v in layout(head).items()) else ""


def free_space(path: str) -> str:
    """'123 GB free' on the disk that holds `path` (or its nearest existing parent)."""
    p = Path(path).expanduser()
    while not p.exists() and p != p.parent:
        p = p.parent
    try:
        return f"{shutil.disk_usage(p).free / 1e9:.0f} GB free"
    except OSError:
        return ""


def checks(cfg: dict) -> list[dict]:
    """What is installed: the AI tools, Tesseract and ffmpeg. [{key, name, ok, detail}]"""
    out = [{"key": "claude", "name": "Claude Code", "ok": bool(shutil.which("claude")),
            "detail": "Installed." if shutil.which("claude") else "Not installed: claude.com/claude-code"}]
    for key, name, (ok, detail) in (("codex", "Codex CLI", codex_cli.check()),
                                    ("gemini", "Gemini CLI", gemini_cli.check(_key("gemini"))),
                                    ("local", "Local model server", local.check(cfg["ai"]["local_url"], _key("local")))):
        out.append({"key": key, "name": name, "ok": ok, "detail": detail})
    exe = tools.tesseract(cfg)
    out.append({"key": "tesseract", "name": "Tesseract (text on screen)", "ok": bool(exe),
                "detail": "Installed." if exe else f"Not installed. Without it, text in videos and slides isn't read. "
                                                   f"To install it: {tools.install_hint('tesseract')}"})
    out.append({"key": "ffmpeg", "name": "ffmpeg (video)", "ok": True,
                "detail": "Installed." if shutil.which("ffmpeg") else "Using the copy that comes with the app."})
    return out


def _key(account: str) -> str | None:
    try:
        return secrets.get_key(account)
    except Exception:  # no keychain (e.g. a server without a desktop): treat as no key
        return None


def ocr_choices(cfg: dict) -> list[dict]:
    """The OCR languages Tesseract has, with readable names: [{code, name, on}]."""
    exe = tools.tesseract(cfg)
    have = tools.tesseract_langs(exe, cfg["ocr"].get("tessdata", "")) if exe else []
    chosen = set(cfg["ocr"]["langs"].split("+"))
    return [{"code": c, "name": LANGUAGES.get(c, c), "on": c in chosen} for c in have]


def form_defaults(cfg: dict) -> dict:
    """The setup form's starting values: the current config, or good first choices."""
    vaults = obsidian_vaults()
    first = not config.is_set_up(cfg)
    return {"vault": str(config.brain_dir(cfg)) if not first else (vaults[0]["path"] if vaults else ""),
            "folder": "Rot2Gold" if first else current_folder(cfg),
            "git": cfg["vault"]["git"] != "off",
            "data_dir": str(config.data_dir(cfg)),
            "provider": ai.provider(cfg), "backend": cfg["notes"]["backend"], "model": cfg["notes"]["model"],
            "local_url": cfg["ai"]["local_url"], "language": cfg["notes"]["language"],
            "ocr_langs": cfg["ocr"]["langs"].split("+"), "collection": "", "browser": "firefox",
            "launcher": first, "move_data": True}


def validate(values: dict, cfg: dict) -> tuple[dict, list[str]]:
    """Check the form. Returns (the config changes, errors)."""
    errors, changes = [], {}
    vault_dir = Path(values.get("vault", "").strip()).expanduser()
    if not values.get("vault", "").strip():
        errors.append("Choose your Obsidian vault.")
    elif not vault_dir.is_dir():
        errors.append(f"The vault folder {vault_dir} doesn't exist.")
    elif not os.access(vault_dir, os.W_OK):
        errors.append(f"The vault folder {vault_dir} can't be written to.")
    folder = values.get("folder", "").strip()
    if folder and (any(c in folder for c in '/\\:*?"<>|') or folder.startswith(".")):
        errors.append("The folder name can't contain / \\ : * ? \" < > | or start with a dot.")
    vault_cfg = {"path": str(vault_dir), "git": "auto" if values.get("git") else "off"}
    if folder or not config.is_set_up(cfg):
        vault_cfg |= layout(folder or "Rot2Gold")
    changes["vault"] = vault_cfg

    data = Path(values.get("data_dir", "").strip() or default_data_dir()).expanduser()
    if vault_dir.is_dir() and (data == vault_dir or vault_dir in data.parents):
        errors.append("Keep videos and other content outside the vault, or Obsidian would index every video.")
    try:
        data.mkdir(parents=True, exist_ok=True)
        if not os.access(data, os.W_OK):
            errors.append(f"The folder {data} can't be written to.")
    except OSError as exc:
        errors.append(f"Can't create {data}: {exc.strerror}.")
    changes["storage"] = {"data_dir": "" if data == default_data_dir() else str(data)}

    provider = values.get("provider", "claude")
    if provider not in ai.PROVIDERS:
        errors.append("Choose who writes the notes.")
    model = values.get("model", "").strip()
    changes["ai"] = {"provider": provider}
    changes["notes"] = {"model": model, "language": values.get("language", "").strip() or "English"}
    changes["ideas"] = {"model": model}
    if provider == "claude":
        backend = values.get("backend", "subscription")
        changes["notes"]["backend"] = backend if backend in ("subscription", "api") else "subscription"
        if backend == "api" and not values.get("key") and not _key("anthropic"):
            errors.append("Enter your Anthropic API key, or use your Claude subscription.")
    if provider == "local":
        url = values.get("local_url", "").strip() or local.DEFAULT_URL
        if not url.startswith(("http://", "https://")):
            errors.append("The local server address starts with http:// or https://.")
        if not model:
            errors.append("Choose the local model that writes the notes.")
        changes["ai"]["local_url"] = url
    langs = [code for code in values.get("ocr_langs", []) if code]
    if langs:
        changes["ocr"] = {"langs": "+".join(langs)}

    url = values.get("collection", "").strip()
    if url:
        try:
            values["collection"] = sources.get("tiktok").validate_url(url)
        except ValueError as exc:
            errors.append(f"Collection link: {exc}")
        if values.get("browser", "firefox") not in connections.BROWSERS:
            errors.append("Choose the browser you're logged into TikTok with.")
    return changes, errors


def save(values: dict, changes: dict, cfg: dict, report=lambda line: None) -> None:
    """Write the config, store the key, move the data if asked, prepare the vault, add the collection,
    add the launcher. Call only after validate() found no errors."""
    user = config.read_user()
    for section, fields in changes.items():
        user.setdefault(section, {}).update(fields)
    if not user["storage"]["data_dir"]:
        user["storage"].pop("data_dir")
    old_data, new_data = config.data_dir(cfg), Path(changes["storage"]["data_dir"] or default_data_dir()).expanduser()
    if values.get("key"):
        secrets.set_key(ai.KEY_ACCOUNTS[changes["ai"]["provider"]], values["key"])
        report("API key saved in your system keychain.")
    if old_data.resolve() != new_data.resolve() and values.get("move_data") and (old_data / "r2g.sqlite").exists():
        move_data(old_data, new_data)
        report(f"Moved your videos and database to {new_data}.")
    config.write_user(user)
    cfg = config.load()
    if made := vault.prepare(cfg):
        report(f"Created in your vault: {', '.join(made)}.")
    if values.get("collection"):
        con = db.connect(new_data / "r2g.sqlite")
        try:
            cid = connections.add(con, "tiktok", values["collection"], "", "auto", values.get("browser", "firefox"))
            report(f"Added the collection {connections.get(con, cid)['name']}.")
        except ValueError as exc:  # e.g. it already exists
            report(f"The collection wasn't added: {exc}.")
    if values.get("launcher"):
        from . import launcher
        try:
            launcher.install()
            report("Added Rot2Gold to your app menu.")
        except Exception as exc:  # the app works without it
            report(f"The app menu entry couldn't be added: {exc}.")


def move_data(old: Path, new: Path) -> None:
    """Copy the database (consistently, with SQLite's backup), media and logs, check them, then delete the old ones."""
    new.mkdir(parents=True, exist_ok=True)
    # closing(): a sqlite3 connection's own `with` only commits, and Windows can't delete a file still open.
    with closing(sqlite3.connect(old / "r2g.sqlite")) as src, closing(sqlite3.connect(new / "r2g.sqlite")) as dst:
        src.backup(dst)
    for name in ("media", "logs", "ideas-dry-run"):
        if (old / name).is_dir():
            shutil.copytree(old / name, new / name, dirs_exist_ok=True)
    count = lambda root: sum(1 for p in root.rglob("*") if p.is_file())  # noqa: E731
    if (old / "media").is_dir() and count(new / "media") < count(old / "media"):
        raise OSError("not every file was copied; the old folder was left as it was")
    for name in ("media", "logs", "ideas-dry-run"):
        shutil.rmtree(old / name, ignore_errors=True)
    for suffix in ("", "-wal", "-shm"):
        (old / f"r2g.sqlite{suffix}").unlink(missing_ok=True)


def summary(cfg: dict) -> list[tuple[str, str]]:
    """Where things are, for `r2g setup --check` and the Settings card."""
    return [("Config file", str(config.config_file())), ("Vault", str(config.brain_dir(cfg)) if config.is_set_up(cfg) else "not set"),
            ("App folder", config.vault_rel("videos", cfg).rsplit("/", 1)[0]), ("Data folder", str(config.data_dir(cfg))),
            ("AI", ai.PROVIDERS[ai.provider(cfg)]), ("System", f"{platform.system()} {platform.release()}")]
