"""Direct mode, for local models ([ai] provider = "local"): a model without tools can't read files, run `r2g`
or search the web, so the app puts everything in the prompt, gets the answer as JSON, and writes the files.

Notes come out in the same format as an agent's, but simpler: claims are not checked (no web search)
and notes are not linked to each other. Each function returns a Result shaped like an agent's report,
so notes.py and ideas.py carry on exactly as with an agent.
"""

import json
import re
import unicodedata
from datetime import date
from pathlib import Path

import yaml

from . import db, notefile
from .ai import local
from .ai.base import Result
from .config import brain_dir, vault_rel
from .paths import RESOURCES
from .postdata import post_record, post_text
from .vault import prompt_values

LIST = {"type": "array", "items": {"type": "string"}}
# skip_reason comes last: a model fills fields in order, so it decides after reading the post.
NOTE_SCHEMA = {"type": "object", "properties": {
    "title": {"type": "string"}, "description": {"type": "string"},
    "content_language": {"type": "string"}, "topic_tags": LIST, "key_points": LIST, "content": {"type": "string"},
    "mentioned": LIST, "context": {"type": "string"}, "further_reading": LIST, "insights": LIST,
    "theme": {"type": "string"}, "hub_line": {"type": "string"}, "quotes": LIST,
    "skip_reason": {"type": ["string", "null"]}}}
ITEM = {"type": "object", "properties": {
    "kind": {"type": "string", "enum": ["idea", "learning", "event"]},
    "action": {"type": "string", "enum": ["create", "update"]}, "file": {"type": "string"},
    "title": {"type": "string"}, "description": {"type": "string"}, "summary": {"type": "string"},
    "when": {"type": "string"}, "until": {"type": "string"}, "where": {"type": "string"}, "topic_tags": LIST,
    "try_it": LIST,
    "sources": {"type": "array", "items": {"type": "object", "properties": {
        "note": {"type": "string"}, "line": {"type": "string"}}}}}}
IDEAS_SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": ITEM},
                                                 "considered": LIST, "notes": LIST}}

NOTE_CALLOUT = ("> [!note] AI-processed note. The Content section is the creator's words. Everything after it is"
                " AI-written and not verified fact unless a source says so.")
CALLOUTS = {"idea": "> [!note] AI-generated idea drawn from the notes below. Not verified advice.",
            "learning": "> [!note] AI-generated learning drawn from the notes below. Not verified fact.",
            "event": "> [!note] AI-generated event note drawn from the videos below. Dates, places and figures"
                     " are not verified: check them before relying on them."}
SOURCE_SECTIONS = {"idea": "## Why sources point here", "learning": "## What each source adds",
                   "event": "## What each source says"}
DATE = re.compile(r"\d{4}(-\d{2}(-\d{2})?)?")


def slugify(text: str, words: int = 8) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return "-".join(re.findall(r"[a-z0-9]+", ascii_text)[:words]) or "untitled"


def unique_name(name: str, taken) -> str:
    """`name`, or `name-2`, `name-3`, … : file names are unique across the whole vault."""
    candidate, n = name, 1
    while candidate in taken:
        n += 1
        candidate = f"{name}-{n}"
    return candidate


def tag(text: str) -> str:
    return "-".join(re.findall(r"[a-z0-9]+", text.lower()))


def quoted(text: str) -> str:
    """A YAML double-quoted string (JSON's syntax is valid YAML)."""
    return json.dumps(text, ensure_ascii=False)


def bullets(items, empty: str | None = None) -> list[str]:
    lines = [f"- {i.strip()}" for i in items if i and i.strip()]
    return lines or ([empty] if empty else [])


def _section(lines: list[str], heading: str) -> tuple[int, int] | None:
    """(heading index, end index) of a `## ` section, or None."""
    for i, line in enumerate(lines):
        if line.strip().lower() == heading.lower():
            end = next((j for j in range(i + 1, len(lines)) if lines[j].startswith("## ")), len(lines))
            return i, end
    return None


def _ensure_section(lines: list[str], heading: str) -> tuple[int, int]:
    if (found := _section(lines, heading)) is None:
        lines += ["", heading, ""]
        found = _section(lines, heading)
    return found


def add_to_hub(path: Path, theme: str, line: str, new_tags: list[str]) -> list[str]:
    """List a note under its theme and add new topic tags (kept sorted). Returns the tags that were new."""
    lines = path.read_text().splitlines() if path.exists() else []
    start, end = _ensure_section(lines, "## Topic tags in use")
    items = [i for i in range(start + 1, end) if lines[i].startswith("- ")]
    known = [lines[i][2:].strip() for i in items]
    added = [t for t in dict.fromkeys(new_tags) if t and t not in known]
    if added:
        if items:
            at = items[0]
            for i in reversed(items):
                del lines[i]
        else:  # the first tags: after the section's text, a blank line on each side
            at = end
            while at > start + 1 and not lines[at - 1].strip():
                at -= 1
            lines[at:at] = [""]
            at += 1
        tag_lines = [f"- {t}" for t in sorted(known + added)]
        lines[at:at] = tag_lines
        after = at + len(tag_lines)
        if after < len(lines) and lines[after].strip():
            lines.insert(after, "")
    start, end = _ensure_section(lines, "## Posts by theme")
    theme = theme.strip() or "Other"
    head = next((i for i in range(start + 1, end) if lines[i].strip().lower() == f"### {theme}".lower()), None)
    if head is None:
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1
        lines[end:end] = ["", f"### {theme}", ""]
        head = end + 1
        end += 3
    stop = next((i for i in range(head + 1, len(lines)) if lines[i].startswith(("## ", "### "))), len(lines))
    last = max((i for i in range(head + 1, stop) if lines[i].startswith("- ")), default=head + 1)
    lines.insert(last + 1, f"- {line}")
    path.write_text("\n".join(lines).rstrip() + "\n")
    return added


def hub_lists(path: Path) -> tuple[list[str], list[str]]:
    """(topic tags, themes) from the hub note."""
    lines = path.read_text().splitlines() if path.exists() else []
    tags, themes = [], []
    if (found := _section(lines, "## Topic tags in use")):
        tags = [lines[i][2:].strip() for i in range(*found) if lines[i].startswith("- ")]
    if (found := _section(lines, "## Posts by theme")):
        themes = [lines[i][4:].strip() for i in range(*found) if lines[i].startswith("### ")]
    return tags, themes


def has_words(post: dict) -> bool:
    """Enough speech or on-screen text to be worth a note: about a sentence of either."""
    spoken = sum(len((s.get("text") or "").split()) for s in post["transcript"])
    shown = sum(len((i.get("ocr_text") or "").split()) for i in post["images"])
    return spoken >= 15 or shown >= 15


TIMESTAMP = re.compile(r"^\[\d+:\d+(\.\d+)?\s*[–-]\s*\d+:\d+(\.\d+)?\]\s*", re.M)


def tidy(content: str) -> str:
    """The model's Content section without leftover timestamps, and with a blank line after each heading."""
    content = TIMESTAMP.sub("", content)
    return re.sub(r"^(#{1,6} [^\n]*)\n(?!\n)", r"\1\n\n", content.strip(), flags=re.M)


def render_note(post: dict, platform: str, a: dict, today: str) -> str:
    tags = [platform or "post"] + [t for t in (tag(x) for x in a.get("topic_tags", [])[:3]) if t]
    front = ["---", f"description: {quoted(a.get('description', ''))}", f"source: {post['url']}",
             f"creator: {quoted('@' + (post['creator'] or 'unknown'))}", f"posted: {post['posted'] or ''}",
             f"processed: {today}", f"type: {post['type'] or 'video'}", f"language: {a.get('content_language') or 'und'}",
             f'post_id: "{post["id"]}"', "tags:", *[f"  - {t}" for t in dict.fromkeys(tags)], "---", ""]
    body = [f"# {a.get('title') or 'Untitled post'}", "", NOTE_CALLOUT, "", "## Key points", "",
            *bullets(a.get("key_points", [])), "", "## Content", "", tidy(a.get("content") or "No text."), "",
            "## References", "", "**Mentioned**", "", *bullets(a.get("mentioned", []), "None."), "",
            "**Checked**", "", "Not checked: written by a local model without web search.", "",
            "## Context and other perspectives", "", (a.get("context") or "").strip()]
    if a.get("further_reading"):
        body += ["", "Further reading:", *bullets(a["further_reading"][:3])]
    body += ["", "## Insights", "", *bullets(a.get("insights", []), "None."), "", "## My notes", ""]
    return "\n".join(front + body)


def _add(total: Result, part: Result) -> None:
    total.turns += part.turns
    total.duration_ms += part.duration_ms
    for k in total.usage:
        total.usage[k] += part.usage.get(k, 0)


def _render(name: str, **values) -> str:
    text = (RESOURCES / "prompts" / name).read_text()
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text


def write_notes(con, batch: list[str], cfg: dict, on_line=lambda line: None, api_key: str | None = None) -> Result:
    """Write a note for each post in `batch`, like an agent's batch: note, hub, quotes, then done or skipped."""
    root, today = brain_dir(cfg), date.today().isoformat()
    hub, quotes = root / vault_rel("hub", cfg), root / vault_rel("quotes", cfg)
    total = Result(ok=True, structured={"posts": [], "new_tags": [], "disputed": [], "problems": []})
    for pid in batch:
        row = con.execute("SELECT * FROM posts WHERE id = ?", (pid,)).fetchone()
        post = post_record(con, row)
        tags, themes = hub_lists(hub)
        prompt = _render("direct-note.md", post=post_text(post), tags=", ".join(tags) or "(none yet)",
                         themes=", ".join(themes) or "(none yet)", today=today,
                         note_language=prompt_values(cfg)["note_language"])
        res = local.chat(prompt, schema=NOTE_SCHEMA, model=cfg["notes"]["model"], url=cfg["ai"]["local_url"], api_key=api_key)
        _add(total, res)
        a = res.structured or {}
        if not res.ok:
            total.structured["problems"].append(f"{pid}: {res.error}")
            continue
        if a.get("skip_reason") and has_words(post):  # small models skip too eagerly: only an empty post is skipped
            on_line(f"{pid}: the model wanted to skip it ({a['skip_reason'][:80]}), but it has speech or text: writing it")
            a["skip_reason"] = None
        if a.get("skip_reason"):
            db.set_status(con, pid, "skipped", skip_reason=a["skip_reason"][:200])
            total.structured["posts"].append({"id": pid, "note_path": None, "skip_reason": a["skip_reason"]})
            on_line(f'r2g skip {pid} "{a["skip_reason"][:80]}"')
            continue
        name = unique_name(f"video-{slugify(a.get('title', ''))}", notefile.brain_names())
        rel = f"{vault_rel('videos', cfg)}/{name}.md"
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(render_note(post, row["platform"], a, today))
        on_line(f"write {name}.md")
        added = add_to_hub(hub, a.get("theme", ""), f"[[{name}]] — {a.get('hub_line', '').strip()}",
                           [tag(t) for t in a.get("topic_tags", [])[:3]])
        total.structured["new_tags"] += added
        lines = [f'- "{q.strip()}" — @{post["creator"] or "unknown"}, [[{name}]]' for q in a.get("quotes", [])[:3] if q.strip()]
        if lines:
            with open(quotes, "a") as f:
                f.write("\n".join(lines) + "\n")
        db.set_status(con, pid, "done", note_path=rel, skip_reason=None)
        total.structured["posts"].append({"id": pid, "note_path": rel, "skip_reason": None})
        on_line(f"r2g done {pid} {rel}")
    return total


# ── Ideas, learnings and events ──────────────────────────────────────────────

def note_digest(path: Path, limit: int = 1500) -> str:
    """What the ideas prompt shows of a note: its title, description, key points and insights."""
    note = notefile.read(path)
    keep, inside = [], False
    for line in note.body.splitlines():
        if line.startswith("## "):
            inside = line.strip() in ("## Key points", "## Insights")
        elif inside and line.strip():
            keep.append(line)
    text = f"{note.title} — {note.meta.get('description', '')}\n" + "\n".join(keep)
    return text[:limit]


def _split(text: str) -> tuple[dict, str]:
    if text.startswith("---\n") and (end := text.find("\n---\n", 4)) != -1:
        return yaml.safe_load(text[4:end]) or {}, text[end + 5:]
    return {}, text


def _scalar(value) -> str:
    """A front matter value in the templates' style: dates and numbers bare, text quoted when YAML needs it."""
    if value is None:
        return ""
    if isinstance(value, (bool, int, float, date)):
        return str(value).lower() if isinstance(value, bool) else str(value)
    text = str(value)
    if DATE.fullmatch(text):
        return text
    plain = text and re.fullmatch(r"[\w][\w .,'()/-]*", text) and text.lower() not in ("yes", "no", "true", "false", "null")
    return text if plain else quoted(text)


def _join(meta: dict, body: str) -> str:
    """Front matter like the templates write it (block lists indented two spaces), then the body."""
    out = ["---"]
    for key, value in meta.items():
        if isinstance(value, list):
            out.append(f"{key}:")
            out += [f"  - {_scalar(v)}" for v in value]
        else:  # the rules ask for the description always in double quotes
            out.append(f"{key}: {quoted(str(value)) if key == 'description' else _scalar(value)}".rstrip())
    return "\n".join(out) + "\n---\n" + body


def new_item(item: dict, kind: str, sources: list[dict], names: dict, today: str) -> str:
    links = [s["note"] for s in sources]
    meta = {"description": item["description"], "created": today, "updated": today}
    if kind == "event":
        meta |= {k: (item.get(k) or "") if DATE.fullmatch(item.get(k) or "") or k == "where" else ""
                 for k in ("when", "until", "where")}
    meta |= {"support": notefile.support(links, names), "sources": [f"[[{s}]]" for s in links], "status": "new",
             "tags": [kind] + [t for t in (tag(x) for x in item.get("topic_tags", [])[:2]) if t]}
    actions = _try_lines(item) if kind == "learning" else []
    body = [f"# {item['title']}", "", CALLOUTS[kind], "", item.get("summary", "").strip(), "", SOURCE_SECTIONS[kind], "",
            *[f"- [[{s['note']}]] — {s['line'].strip()}" for s in sources], "",
            *(["## Try it", "", *actions, ""] if actions else []), "## Log", "",
            f"- {today} — created from " + ", ".join(f"[[{s}]]" for s in links), "", "## My notes", ""]
    return _join(meta, "\n" + "\n".join(body))


def _try_lines(item: dict) -> list[str]:
    """A learning's "## Try it" lines: what its sources suggest doing, each once."""
    lines = [f"- {line.strip().removeprefix('- ').strip()}" for line in item.get("try_it") or [] if line.strip(" -")]
    return list({line.lower(): line for line in reversed(lines)}.values())[::-1]


def update_item(text: str, kind: str, sources: list[dict], names: dict, today: str, item: dict | None = None) -> str | None:
    """Add new sources (and, for a learning, new Try it lines) to an existing item; None if no source is new.
    Title, status and the user's notes stay."""
    item = item or {}
    meta, body = _split(text)
    have = [str(s).strip("[]") for s in (meta.get("sources") or [])]
    fresh = [s for s in sources if s["note"] not in have]
    if not fresh:
        return None
    meta["sources"] = [f"[[{s}]]" for s in have + [s["note"] for s in fresh]]
    meta["support"] = notefile.support(have + [s["note"] for s in fresh], names)
    meta["updated"] = today
    lines = body.splitlines()
    heading = SOURCE_SECTIONS[kind]
    if (found := _section(lines, heading)) is None:
        log = _section(lines, "## Log")
        at = log[0] if log else len(lines)
        lines[at:at] = [heading, "", ""]
        found = _section(lines, heading)
    start, end = found
    last = max((i for i in range(start + 1, end) if lines[i].startswith("- ")), default=start + 1)
    lines[last + 1:last + 1] = [f"- [[{s['note']}]] — {s['line'].strip()}" for s in fresh]
    if kind == "learning" and (actions := _try_lines(item)):
        if _section(lines, "## Try it") is None:  # a new section goes just before the Log
            log = _section(lines, "## Log")
            at = log[0] if log else len(lines)
            lines[at:at] = ["## Try it", "", ""]
        start, end = _section(lines, "## Try it")
        have_lines = {line.strip().lower() for line in lines[start + 1:end]}
        last = max((i for i in range(start + 1, end) if lines[i].startswith("- ")), default=start + 1)
        lines[last + 1:last + 1] = [a for a in actions if a.lower() not in have_lines]
    start, end = _ensure_section(lines, "## Log")
    first = next((i for i in range(start + 1, end) if lines[i].strip()), start + 1)
    lines.insert(first, f"- {today} — new support: " + ", ".join(f"[[{s['note']}]]" for s in fresh))
    return _join(meta, "\n".join(lines) + "\n")


def find_ideas(con, batch: list[str], needs: dict, known: dict, cfg: dict, folder: Path | None,
               on_line=lambda line: None, api_key: str | None = None) -> Result:
    """One ideas batch: the model proposes items as JSON; the app writes them into their folders,
    or into `folder` in a dry run. Returns a Result shaped like the agent's report."""
    from .ideas import KINDS, catalog, kind_dir, look_for
    root, today = brain_dir(cfg), date.today().isoformat()
    rows = {r["id"]: r["note_path"] for r in con.execute(
        f"SELECT id, note_path FROM posts WHERE id IN ({db.placeholders(batch)})", batch)}
    names = notefile.brain_names()
    blocks = []
    for pid in batch:
        path = root / (rows.get(pid) or "")
        if rows.get(pid) and path.is_file():
            blocks.append(f"### {pid} · {path.stem} · [{look_for(needs.get(pid, {}))}]\n{note_digest(path)}")
    prompt = _render("direct-ideas.md", notes="\n\n".join(blocks) or "(none)", today=today,
                     existing=catalog(known["idea"]), existing_learnings=catalog(known["learning"]),
                     existing_events=catalog(known["event"]), note_language=prompt_values(cfg)["note_language"],
                     max_new=cfg["ideas"]["max_new_per_pass"],
                     max_new_learnings=cfg["ideas"].get("max_new_learnings_per_pass", 8),
                     max_new_events=cfg["ideas"].get("max_new_events_per_pass", 8))
    res = local.chat(prompt, schema=IDEAS_SCHEMA, model=cfg["ideas"]["model"], url=cfg["ai"]["local_url"], api_key=api_key)
    if not res.ok:
        return res
    answer, report = res.structured, {"created": [], "updated": [], "considered": [], "notes": []}
    limits = {"idea": cfg["ideas"]["max_new_per_pass"], "learning": cfg["ideas"].get("max_new_learnings_per_pass", 8),
              "event": cfg["ideas"].get("max_new_events_per_pass", 8)}
    held_back = set()
    by_note = {Path(p).stem: pid for pid, p in rows.items() if p}
    for item in answer.get("items", []):
        kind = item.get("kind")
        if kind not in KINDS:
            continue
        sources = [s for s in item.get("sources", []) if s.get("note", "").removesuffix(".md") in names]
        for s in sources:
            s["note"] = s["note"].removesuffix(".md")
        if not sources:
            on_line(f"skipped “{item.get('title', '')}”: none of its sources is a note in the vault")
            continue
        target_dir = folder or kind_dir(kind)
        target_dir.mkdir(parents=True, exist_ok=True)
        existing = {i["name"]: i["path"] for i in known[kind]}
        name = (item.get("file") or "").removesuffix(".md")
        if item.get("action") == "update" and name in existing:
            current = target_dir / f"{name}.md" if (target_dir / f"{name}.md").is_file() else existing[name]
            text = update_item(current.read_text(), kind, sources, names, today, item)
            if text:
                (target_dir / f"{name}.md").write_text(text)
                report["updated"].append(str(target_dir / f"{name}.md"))
                on_line(f"edit {name}.md")
            continue
        if limits[kind] <= 0:  # over the limit: its notes wait for the next pass
            held_back.update(by_note.get(s["note"]) for s in sources)
            continue
        limits[kind] -= 1
        name = unique_name(f"{kind}-{slugify(item.get('title', ''))}", set(names) | set(existing)
                           | {p.stem for p in target_dir.glob("*.md")})
        (target_dir / f"{name}.md").write_text(new_item(item, kind, sources, names, today))
        report["created"].append(str(target_dir / f"{name}.md"))
        on_line(f"write {name}.md")
    report["considered"] = [pid for pid in answer.get("considered", []) if pid in rows and pid not in held_back]
    report["notes"] = answer.get("notes", [])
    res.structured = report
    return res
