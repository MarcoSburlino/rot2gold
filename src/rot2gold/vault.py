"""The app's place in the user's vault: its folders, templates and starter notes, and how prompts describe them."""

import shutil

from .config import DATA, ConfigError, brain_dir, load, vault_rel
from .paths import RESOURCES

TEMPLATES = ("video-note.md", "idea-note.md", "learning-note.md", "event-note.md")
FOLDERS = ("videos", "ideas", "learnings", "events", "templates")
STARTERS = {"hub": "hub.md", "quotes": "quotes.md"}


def prepare(cfg: dict | None = None) -> list[str]:
    """Create what is missing: the folders, the templates, the hub and quotes notes. Never overwrites a file.
    Returns the paths created, relative to the vault."""
    cfg = cfg or load()
    root = brain_dir(cfg)
    if not root.is_dir():
        raise ConfigError(f"The vault folder {root} does not exist. Choose it again in Settings → Setup.")
    made = []
    for key in FOLDERS:
        folder = root / vault_rel(key, cfg)
        if not folder.is_dir():
            folder.mkdir(parents=True)
            made.append(vault_rel(key, cfg) + "/")
    sources = [(RESOURCES / "templates" / name, f"{vault_rel('templates', cfg)}/{name}") for name in TEMPLATES]
    sources += [(RESOURCES / "starter" / name, vault_rel(key, cfg)) for key, name in STARTERS.items()]
    for source, rel in sources:
        target = root / rel
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            made.append(rel)
    return made


def prepare_and_report(cfg: dict, report) -> None:
    if made := prepare(cfg):
        report(f"created in your vault: {', '.join(made)}")


def where(cfg: dict | None = None) -> str:
    """The "Where things are" block every prompt carries: the names the rules use, with real paths."""
    cfg = cfg or load()
    root = brain_dir(cfg)
    lines = ["Where things are (the rules refer to these by name):",
             f"- The vault: {root}",
             f"- The videos folder: {root / vault_rel('videos', cfg)} (for `r2g done`, note paths are relative to the vault:"
             f" {vault_rel('videos', cfg)}/video-<slug>.md)",
             f"- The hub note: {root / vault_rel('hub', cfg)}",
             f"- The quotes note: {root / vault_rel('quotes', cfg)}",
             f"- The ideas folder: {root / vault_rel('ideas', cfg)}",
             f"- The learnings folder: {root / vault_rel('learnings', cfg)}",
             f"- The events folder: {root / vault_rel('events', cfg)}",
             f"- The templates folder: {root / vault_rel('templates', cfg)} ({', '.join(TEMPLATES)})",
             f"- The rules: {RESOURCES / 'rules'}",
             f"- Post images: under {DATA / 'media'} (each post's image paths are in `r2g pending`)"]
    if cfg["vault"]["rules"]:
        lines.append(f"- The user's own rules for their vault: {root / vault_rel('rules', cfg)}. Follow them too.")
    return "\n".join(lines)


def prompt_values(cfg: dict | None = None) -> dict:
    """Values every prompt template can use."""
    cfg = cfg or load()
    root = brain_dir(cfg)
    examples = [str(root / p) for p in cfg["notes"]["examples"]] or [str(RESOURCES / "examples/video-note-example.md")]
    user_rules = (f"\n   Also read the user's own rules for their vault, {root / vault_rel('rules', cfg)}, and follow them."
                  if cfg["vault"]["rules"] else "")
    return {"where": where(cfg), "rules": str(RESOURCES / "rules"), "user_rules": user_rules,
            "examples": " and ".join(examples), "note_language": cfg["notes"]["language"],
            "vault": str(root), "videos": vault_rel("videos", cfg)}
