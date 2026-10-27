"""Fold ideas into the learnings they put into practice (Gold, decided 2026-10-27).

Most ideas were the "do it" side of a learning that says the same thing ("Build confidence from a
stack of proof" ↔ "Confidence grows from your own successes"). Merging moves the idea's action under
its learning's "## Try it", brings its sources and the user's own notes along, points links to the
idea at the learning, and removes the idea file. The vault's formatting is kept: only the lines that
change are touched. Run it as one recorded run with one vault commit, so Undo reverts it.
"""

import re
from datetime import date

from . import ideas
from .direct import _section

LINK = re.compile(r"\[\[([^\]|#]+)")
# Where a new "## Try it" goes: before the first of these sections (the learning note format's order).
AFTER_TRY = ("## Events that show it", "## Related learnings", "## Log", "## My notes")


def plan() -> dict:
    """Which idea folds into which learning. An idea folds into a learning it is linked with (either
    way); with several, the one sharing the most sources. Ideas with no learning stay: they are pure
    actions. Dropped ideas stay too, so merging never brings back something the user set aside."""
    learnings = {item["name"]: item for item in ideas.list_items("learning")}
    texts = {name: item["path"].read_text() for name, item in learnings.items()}
    pairs, alone, dropped = [], [], []
    for idea in ideas.list_items("idea"):
        mentioned = [n for n in LINK.findall(idea["path"].read_text()) if n in learnings]
        linked = list(dict.fromkeys(mentioned + [n for n, text in texts.items() if f"[[{idea['name']}" in text]))
        if not linked:
            alone.append(idea)
        elif idea["status"] == "dropped":
            dropped.append(idea)
        else:
            # Shared sources and shared title words: "Reason from first principles on irreversible decisions"
            # belongs with "Irreversible decisions deserve care", even if another learning shares more videos.
            score = lambda n: (len(set(learnings[n]["sources"]) & set(idea["sources"]))
                               + len(_words(learnings[n]["title"]) & _words(idea["title"])))
            best = max(linked, key=lambda n: (score(n), -linked.index(n)))
            pairs.append({"idea": idea, "learning": learnings[best],
                          "new_sources": [s for s in idea["sources"] if s not in learnings[best]["sources"]],
                          "also_linked": [learnings[n]["title"] for n in linked if n != best]})
    return {"pairs": pairs, "alone": alone, "dropped": dropped}


def _words(title: str) -> set[str]:
    """The words of a title that carry meaning (longer than 3 letters)."""
    return {w for w in re.findall(r"[a-z]+", title.lower()) if len(w) > 3}


def _split(text: str) -> tuple[list[str], list[str]]:
    """(front matter lines, body lines) of a note that starts with a --- block."""
    lines = text.split("\n")
    end = lines.index("---", 1)
    return lines[1:end], lines[end + 1:]


def _paragraph(body: list[str]) -> str:
    """The text under an idea's title: its lines before the first section, without the callout."""
    start = next(i for i, line in enumerate(body) if line.startswith("# ")) + 1
    end = next((i for i in range(start, len(body)) if body[i].startswith("## ")), len(body))
    return " ".join(line.strip() for line in body[start:end] if line.strip() and not line.startswith(">"))


def _section_lines(body: list[str], heading: str) -> list[str]:
    found = _section(body, heading)
    return body[found[0] + 1:found[1]] if found else []


def fold(idea: dict, learning: dict, today: str) -> str:
    """The learning's new text with the idea folded in."""
    _, idea_body = _split(idea["path"].read_text())
    front, body = _split(learning["path"].read_text())
    new = [s for s in idea["sources"] if s not in learning["sources"]]

    # Front matter: the idea's other sources, today's date, and the idea's status if the user had set one.
    at = next(i for i, line in enumerate(front) if line.startswith("sources:")) + 1
    while at < len(front) and front[at].startswith("  - "):
        at += 1
    front[at:at] = [f'  - "[[{s}]]"' for s in new]
    front = [f"updated: {today}" if line.startswith("updated:") else line for line in front]
    if learning["status"] == "new" and idea["status"] in ("trying", "kept"):
        front = [f"status: {idea['status']}" if line.startswith("status:") else line for line in front]

    # What the idea's sources add, for the sources that are new to the learning.
    adds = [line for line in _section_lines(idea_body, "## Why sources point here")
            if line.startswith("- [[") and LINK.match(line[2:]) and LINK.match(line[2:]).group(1) in new]
    if adds and (found := _section(body, "## What each source adds")):
        last = max((i for i in range(found[0] + 1, found[1]) if body[i].startswith("- ")), default=found[0] + 1)
        body[last + 1:last + 1] = adds

    # Try it: the old "## Use it" becomes it; the bare link to this idea goes; the idea's action comes in.
    if _section(body, "## Try it") is None and (old := _section(body, "## Use it")):
        body[old[0]] = "## Try it"
    bare = re.compile(r"^- \[\[" + re.escape(idea["name"]) + r"(\|[^\]]*)?\]\]\s*$")
    body = [line for line in body if not bare.match(line)]
    if _section(body, "## Try it") is None:
        before = next((i for i, line in enumerate(body) if line.strip() in AFTER_TRY), len(body))
        body[before:before] = ["## Try it", "", ""]
    found = _section(body, "## Try it")
    last = max((i for i in range(found[0] + 1, found[1]) if body[i].startswith("- ")), default=found[0] + 1)
    body[last + 1:last + 1] = [f"- **{idea['title']}.** {_paragraph(idea_body)}".rstrip()]

    # Log, newest first.
    log = _section(body, "## Log")
    if log:
        first = next((i for i in range(log[0] + 1, log[1]) if body[i].strip()), log[0] + 1)
        body.insert(first, f"- {today} — merged in the idea “{idea['title']}”: its action is under Try it"
                    + (f", with {len(new)} more {'source' if len(new) == 1 else 'sources'}" if new else ""))

    # The user's own notes on the idea are never lost.
    mine = "\n".join(_section_lines(idea_body, "## My notes")).strip()
    if mine:
        notes = _section(body, "## My notes")
        if notes is None:
            body += ["", "## My notes", ""]
            notes = _section(body, "## My notes")
        body[notes[1]:notes[1]] = ["", f"From the idea “{idea['title']}”:", "", mine, ""]

    text = "---\n" + "\n".join(front) + "\n---\n" + "\n".join(body)
    return re.sub(r"\n{3,}", "\n\n", text)


def _relink(old: str, new: str) -> list[str]:
    """Point links to `old` at `new` in every idea, learning and event file; returns the files changed."""
    pattern = re.compile(r"\[\[" + re.escape(old) + r"(?=[\]|#])")
    changed = []
    for kind in ideas.KINDS:
        for path in ideas.kind_dir(kind).glob(f"{kind}-*.md"):
            text = path.read_text()
            fixed = pattern.sub(f"[[{new}", text)
            if fixed != text:
                path.write_text(fixed)
                changed.append(path.name)
    return changed


def merge(report, today: str | None = None) -> list[dict]:
    """Fold every planned idea into its learning (the caller commits). Returns the pairs merged."""
    today = today or date.today().isoformat()
    done = []
    names = None
    for pair in plan()["pairs"]:
        idea, learning = pair["idea"], pair["learning"]
        # Re-read the learning: an earlier idea in this run may have changed it.
        learning = next(item for item in ideas.list_items("learning") if item["name"] == learning["name"])
        learning["path"].write_text(fold(idea, learning, today))
        idea["path"].unlink()
        relinked = _relink(idea["name"], learning["name"])
        if names is None:
            from . import notefile
            names = notefile.brain_names()
        ideas.recount(learning["path"], names)
        report(f"merged idea {idea['name']} into {learning['name']}"
               + (f"; links updated in {', '.join(relinked)}" if relinked else ""))
        done.append(pair)
    return done
