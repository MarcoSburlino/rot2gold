# The ideas pass

Rules for finding ideas across Marco's notes and writing them as idea notes in his brain. Every agent and every backend (`claude -p` on the subscription or with an API key, or a person running Claude Code or Codex by hand) follows this file, so ideas come out the same way each time.

Read the brain's rules first: `~/Projects/brain/AGENTS.md`, especially "Writing notes" and "Commonplace".

## What an idea is

An idea is **a concrete thing Marco could do**: a practice to try, a method, a tool, a book to read, a project or business idea. It is written as an action ("Try the Feynman technique on the next topic I study"), not as a topic ("Learning").

Its value comes from its **sources**: the notes that point to it. An idea that several independent sources point toward is stronger than an idea from one post.

What is *not* an idea: a quote, an opinion to agree with, a fact, a general theme ("stoicism"), or a purchase someone is promoting.

## History

On the first full run (2026-10-15), each batch agent decided per post whether it held "an idea Marco could act on", and if so wrote `Inbox/idea-<slug>.md`: a title as an action, 1–3 lines, and `From [[video-<slug>]].` That made 15 ideas, each with exactly one source; one was later archived. The video notes themselves linked to each other a lot (Related notes, Insights), but no step looked across notes for shared ideas.

This file replaces that per-post step with one pass that looks across sources. It keeps the old format's spirit: a short action title, a few lines of why, and links to where it came from.

## When the pass runs

- **Inside each Extract**, right after its notes are written and committed: the same run, not a separate step. Input: unchecked notes (`ideas_checked_at` is empty in `data/vn.sqlite`) marked done on or after `[ideas] since` (2026-10-19 by default).
- **"Rebuild ideas"**, started by hand from the app or CLI. Input: unchecked notes under selected themes in `commonplace.md`, regardless of date, in batches of 25. Marco chose Mindset and self-help, Learning and memory, and Money and business on 2026-10-19. Marking only considered notes lets a stopped rebuild resume.
- **Dry runs** write previews to `data/ideas-dry-run/run-N/`, without marking posts or committing to the brain.

The app gives the agent the list of notes to consider. The agent only writes idea notes; the app runs `brain-index`, commits, and records which posts were considered.

## Where ideas live

- Folder: `~/Projects/brain/Inbox/ideas/`.
- File: `idea-<slug>.md`. The slug comes from the title: lowercase, words joined by dashes, ASCII, at most about 8 words. Names must be unique across the whole vault: check with `find ~/Projects/brain -name "idea-<slug>.md"`, and add `-2` if taken.
- Template: `~/Projects/brain/System/templates/idea-note.md`.

## Update first, create last

Marco wants **a few ideas that grow** as more videos point to them, not a new idea every time he extracts (his request, 2026-10-20). So in every pass, inside every Extract:

- A note that **fits an existing idea updates it**. It fits when it supports the same goal or practice, even from a different angle, with a different method to reach the same thing, or as a narrower or broader version of it. "Explain a topic out loud to find the gaps" fits "Try the Feynman technique"; another clip about writing down long-term goals fits "Write a five-year plan"; a different speaker making the same point fits.
- If several existing ideas fit, update only the **closest** one (the same action first, then the same goal).
- A **dropped** idea still counts: a note that fits it records its support there and never creates a near-copy.
- **Create a new idea only when no existing idea fits**: the note points to a different action, one where doing it would not mostly mean doing an existing idea.
- Notes in the same pass that point to the same new action become **one** new idea with several sources.

The prompt lists every existing idea (file, title, description, status, sources), so each candidate is compared with all of them before anything is created.

## Steps

1. **Read what exists.** Start from the list of existing ideas in the prompt; open an idea's full note when a candidate might fit it.
2. **Read the notes to consider**, one at a time. For each, ask: does it contain a concrete action (see "What an idea is")? Note it as a candidate with the note as its source. Most notes have none; that is normal.
3. **Look for support** for each candidate:
   - older video notes: `commonplace.md` (themes and tags), then `rg -il "<term>" ~/Projects/brain/Resources/commonplace/videos`;
   - the rest of the brain: `rg -il "<term>" ~/Projects/brain/Projects ~/Projects/brain/Areas ~/Projects/brain/Resources`. A project note that already does or plans something similar counts (e.g. [[hejdansk]] for spaced repetition);
   - never read `~/Private`, `~/.local/share/chat-vault`, or any path the global rules forbid.
4. **Match before creating** (see "Update first, create last"). For each candidate, find the existing idea it fits best.
   - **Fits → update** that idea (below). Never create a second note for it.
   - **Nothing fits → it may become a new idea** (step 5). If it is related to an existing idea without fitting it, link the two under `## Related ideas` in both.
5. **Decide whether to create.** Only for candidates that fit no existing idea. Create a new idea when:
   - **two or more independent sources** point to it, or
   - **one source** describes a clearly actionable practice, tool, book or project idea (the kind made on the first run). It gets `support: 1` and ranks below multi-source ideas.
   - At most **5 new ideas per pass**. If there are more candidates, keep the best-supported ones, and leave the notes behind the others out of the reported `considered` list, so the next pass sees them again.
6. **Write or update** the notes (format below).
7. **Report** in the JSON format the prompt asks for: created files, updated files, every post id you considered (including those that gave no idea), and in `notes` one line per considered note saying what it led to: `<post id> → updated idea-…`, `<post id> → new idea-… (no existing idea fits: <why>)`, or `<post id> → no idea`.

## Counting sources

- `support` is the number of **independent** sources in `sources:`.
- Each note is one source. A video note and a brain note are both sources.
- Two posts **by the same creator** making the same point count as **one** source (list both, count one).
- Quote slideshows that repeat the same famous quote count as one source per creator, not per post.
- A source that argues *against* the idea goes under `## Tensions`, not in `sources:`, and doesn't count.

## Updating an existing idea

When a new note supports an idea that exists:

- add `"[[<note>]]"` to `sources:` (if it isn't there already);
- add a line under `## Why sources point here`;
- recount `support`;
- set `updated:` to today;
- add a line at the top of `## Log`: `- YYYY-MM-DD — new support: [[<note>]]`;
- if the note adds a different way to do it, you may add one sentence about it to the paragraph under the title ("A later post suggests doing it with …").

Never change the title, the slug, `created`, or `status`. Never remove a source. Never write in `## My notes`. If Marco has set `status: dropped`, still record the new support, but don't reword the idea.

## Note format

```markdown
---
description: <one line, at most ~15 words: the idea and when to open the note>
created: YYYY-MM-DD
updated: YYYY-MM-DD
support: <number of independent sources>
sources:
  - "[[video-…]]"
  - "[[<other note>]]"
status: new
tags:
  - idea
  - <1–2 topic tags from commonplace.md>
---

# <The idea, as an action>

> [!note] AI-generated idea drawn from the notes below. Not verified advice.

<2–4 lines: what to try and why, as the sources put it.>

## Why sources point here

- [[video-a]] — <one line: what this source says that supports the idea>
- [[video-b]] — <…>

## Tensions

- [[video-c]] — <one line: what this source says against it>

## Related ideas

- [[idea-…]]

## Log

- YYYY-MM-DD — created from [[video-a]], [[video-b]]

## My notes

```

- `status` belongs to Marco after creation. Agents write `new` and never change it. Values he may use: `new`, `trying`, `kept`, `dropped`.
- Omit `## Tensions` and `## Related ideas` when empty. Keep `## Log` and `## My notes` (empty) always.
- Tags: block list, lowercase with dashes, always `idea`; reuse topic tags from `commonplace.md`. Never write a `type/` tag (brain-index sets `type/inbox`).
- English throughout. Quotes from a source stay in their original language.

## Tone and honesty

- The title is an action, but the body reports what the sources say: "Three posts recommend…", "The Jim Rohn talk suggests…". No advice of your own beyond what the sources say.
- If a source's note rated a related claim in its **Checked** section, carry the verdict over: "the '65% less anxiety' figure comes from a small commercial study (see the note)". Never present a disputed claim as fact.
- Keep it short. An idea note is a pointer to its sources, not an essay.
- Never invent a source or a link. Every `[[link]]` must be an existing note: check with `find ~/Projects/brain -name "<name>.md"`.

## Migrating the first ideas

The 14 ideas from the first run (`Inbox/idea-*.md`) move into `Inbox/ideas/` with `git mv`, keeping their names, so links to them still work. Each gets the front matter above: `created` and `updated` from the commit that added it, `support: 1`, its one source in `sources:`, `status: new`, tag `idea` plus the topic tags of its source note. Its body becomes the paragraph under the title, followed by `## Why sources point here` with the source, `## Log` with `- <created> — created from [[video-…]] (first run, migrated <today>)`, and an empty `## My notes`. The wording of the old body is kept.
