"""Reading and rendering brain notes for the app.

Notes are markdown with YAML front matter. They are rendered with raw HTML switched off: notes contain
text from posts and the web, and a stray <script> must show as text, never run.
"""

import html
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from markdown_it import MarkdownIt

from .brain import obsidian_uri
from .config import brain_dir

WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]")
md = MarkdownIt("commonmark", {"html": False, "breaks": False}).enable(["table", "strikethrough"])


@dataclass
class Note:
    path: Path
    meta: dict = field(default_factory=dict)
    title: str = ""
    body: str = ""


def read(path: Path, head_only: bool = False) -> Note:
    """Front matter, the first # heading, and the body. head_only reads just the start (for lists)."""
    with open(path, encoding="utf-8") as f:
        text = f.read(4000) if head_only else f.read()
    meta, body = {}, text
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            try:
                meta = yaml.safe_load(text[4:end]) or {}
            except yaml.YAMLError:
                meta = simple_front_matter(text[4:end])
            body = text[end + 4:].lstrip("\n")
    m = re.search(r"^# (.+)$", body, re.M)
    title = m.group(1).strip() if m else path.stem
    if m and not head_only:
        body = body[:m.start()] + body[m.end():]  # the page shows the title itself
    return Note(path, meta if isinstance(meta, dict) else {}, title, body)


def simple_front_matter(text: str) -> dict:
    """Recover plain fields and block lists when a description contains an unquoted colon."""
    out = {}
    key = None
    for line in text.splitlines():
        if line.startswith("  - ") and key is not None and isinstance(out[key], list):
            out[key].append(unquote(line[4:].strip()))
        elif not line.startswith(" ") and ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            out[key] = unquote(value.strip()) if value.strip() else []
    return out


def unquote(value: str) -> str:
    return value[1:-1] if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'" else value


def brain_names() -> dict[str, Path]:
    """Every note in the brain by file name without .md (names are unique across the vault)."""
    root = brain_dir()
    names = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for f in filenames:
            if f.endswith(".md"):
                names.setdefault(f[:-3], Path(dirpath) / f)
    return names


def render(body: str, link_for) -> str:
    """Markdown → HTML. `link_for(name)` gives a URL for [[name]], or None if the note doesn't exist."""
    def wikilink(m):
        name, alias = m.group(1).strip(), (m.group(2) or m.group(1)).strip()
        url = link_for(name)
        label = alias.replace("[", "\\[").replace("]", "\\]")
        return f"[{label}](<{url}>)" if url else label

    out = md.render(WIKILINK.sub(wikilink, body))
    # Obsidian callouts: "> [!note] text" → a styled box.
    out = re.sub(r"<blockquote>\s*<p>\[!(\w+)\]\s*", lambda m: f'<blockquote class="callout callout-{html.escape(m.group(1).lower())}"><p>', out)
    # Links to the web open in a new tab.
    return out.replace('<a href="http', '<a target="_blank" rel="noreferrer" href="http')


def obsidian_link(path: Path) -> str:
    return obsidian_uri(path)
