# The ideas and learnings pass

Rules for finding ideas and learnings across Marco's notes and writing them as notes in his brain. Every agent and every backend (`claude -p` on the subscription or with an API key, or a person running Claude Code or Codex by hand) follows this file, so ideas come out the same way each time.

Read the brain's rules first: `~/Projects/brain/AGENTS.md`, especially "Writing notes" and "Commonplace".

## What an idea is

An idea is **a concrete thing Marco could do**: a practice to try, a method, a tool, a book to read, a project or business idea. It is written as an action ("Try the Feynman technique on the next topic I study"), not as a topic ("Learning").

Its value comes from its **sources**: the notes that point to it. An idea that several independent sources point toward is stronger than an idea from one post.

What is *not* an idea: a quote, an opinion to agree with, a fact, a general theme ("stoicism"), or a purchase someone is promoting.

## What a learning is

A learning is **something understood about how things work**: a principle, a mechanism, a pattern or a finding that a video teaches. It is written as one sentence that states it ("Explaining a topic out loud shows the gaps that rereading hides"), not as a topic ("Learning techniques") and not as an action (that is an idea).

Marco asked for them on 2026-10-20: what did a video teach, does another video say something related, and how do the sources combine into **one shared learning**. So a learning note is written to grow: the first video gives it, later videos that say the same thing (or add evidence, a reason, a limit) are added to it, and its paragraph is rewritten as what the sources say together.

- A learning may come from **one source** (`support: 1`). It is not a copy of that video's Key points or Insights: it is the one reusable lesson, phrased so another video could support it.
- What is *not* a learning: a bare quote, a motivational slogan with no claim in it, a fact about the video itself ("the creator uses subtitles"), or a claim the note's **Checked** section found false. A disputed claim can be a learning only if the note says so in the text ("a small commercial study claims…").
- **Ideas and learnings link up.** When an idea puts a learning into practice, the learning lists it under `## Use it` and the idea lists the learning under `## Learnings behind it`. A note can give an idea, a learning, both, or neither.

## History

On the first full run (2026-10-15), each batch agent decided per post whether it held "an idea Marco could act on", and if so wrote `Inbox/idea-<slug>.md`: a title as an action, 1–3 lines, and `From [[video-<slug>]].` That made 15 ideas, each with exactly one source; one was later archived. The video notes themselves linked to each other a lot (Related notes, Insights), but no step looked across notes for shared ideas.

This file replaces that per-post step with one pass that looks across sources. It keeps the old format's spirit: a short action title, a few lines of why, and links to where it came from.

## When the pass runs

One pass looks for both kinds, in the same Claude call per batch. Each note has two checks in `data/vn.sqlite`: `ideas_checked_at` and `learnings_checked_at`. The prompt tags each note with what to look for in it: `[ideas and learnings]`, or `[learnings]` for a note already checked for ideas.

- **Inside each Extract**, right after its notes are written and committed: the same run, not a separate step. Input: notes not checked for ideas and marked done on or after `[ideas] since` (2026-10-19 by default), then notes of **any age** not checked for learnings. So the Extracts after 2026-10-20 work through the older notes for learnings, 25 per batch, stopping at the plan-usage limit and carrying on next time.
- **"Rebuild ideas"**, started by hand from the app or CLI. Input: notes missing either check, under selected themes in `commonplace.md`, regardless of date, in batches of 25. Marco chose Mindset and self-help, Learning and memory, and Money and business on 2026-10-19. Marking only considered notes lets a stopped rebuild resume.
- **Dry runs** write previews to `data/ideas-dry-run/run-N/`, without marking posts or committing to the brain.

The app gives the agent the list of notes to consider. The agent only writes idea and learning notes; the app runs `brain-index`, commits, and records which posts were considered.

## Where they live

- Ideas: `~/Projects/brain/Inbox/ideas/idea-<slug>.md`, template `~/Projects/brain/System/templates/idea-note.md`.
- Learnings: `~/Projects/brain/Inbox/learnings/learning-<slug>.md`, template `~/Projects/brain/System/templates/learning-note.md`.
- The slug comes from the title: lowercase, words joined by dashes, ASCII, at most about 8 words. Names must be unique across the whole vault: check with `find ~/Projects/brain -name "<file>.md"`, and add `-2` if taken.

## Update first, create last

Marco wants **a few ideas that grow** as more videos point to them, not a new idea every time he extracts (his request, 2026-10-20). So in every pass, inside every Extract:

- A note that **fits an existing idea updates it**. It fits when it supports the same goal or practice, even from a different angle, with a different method to reach the same thing, or as a narrower or broader version of it. "Explain a topic out loud to find the gaps" fits "Try the Feynman technique"; another clip about writing down long-term goals fits "Write a five-year plan"; a different speaker making the same point fits.
- If several existing ideas fit, update only the **closest** one (the same action first, then the same goal).
- A **dropped** idea still counts: a note that fits it records its support there and never creates a near-copy.
- **Create a new idea only when no existing idea fits**: the note points to a different action, one where doing it would not mostly mean doing an existing idea.
- Notes in the same pass that point to the same new action become **one** new idea with several sources.

The prompt lists every existing idea and every existing learning (file, title, description, status, sources), so each candidate is compared with all of them before anything is created.

**Learnings follow the same rules.** A note that says the same thing as an existing learning, from another angle, with other evidence, or as a narrower or broader case, updates the closest learning. Create a new learning only when none fits. When a second source joins a learning, rewrite its paragraph as the **shared learning**: what the sources agree on, what each adds, and how strong the evidence is (a study, a personal story, an opinion). A source that says the opposite goes under `## Where they differ`.

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
5. **Decide whether to create.** Only for candidates that fit no existing idea or learning. A learning may be created from one source; at most **8 new learnings per pass** (`[ideas] max_new_learnings_per_pass`), with the same hold-back rule as ideas below. Create a new idea when:
   - **two or more independent sources** point to it, or
   - **one source** describes a clearly actionable practice, tool, book or project idea (the kind made on the first run). It gets `support: 1` and ranks below multi-source ideas.
   - At most **5 new ideas per pass**. If there are more candidates, keep the best-supported ones, and leave the notes behind the others out of the reported `considered` list, so the next pass sees them again.
6. **Write or update** the notes (format below).
7. **Report** in the JSON format the prompt asks for: created files and updated files (ideas and learnings together; the app tells them apart by the `idea-`/`learning-` prefix), every post id you considered (including those that gave nothing), and in `notes` one line per considered note saying what it led to: `<post id> → updated idea-…; new learning-… (no existing learning fits: <why>)`, or `<post id> → nothing`.

## Counting sources

- `support` is the number of **independent** sources in `sources:`.
- Each note is one source. A video note and a brain note are both sources.
- Two posts **by the same creator** making the same point count as **one** source (list both, count one).
- Quote slideshows that repeat the same famous quote count as one source per creator, not per post.
- A source that argues *against* the idea goes under `## Tensions`, not in `sources:`, and doesn't count.

## Updating an existing idea or learning

When a new note supports an idea that exists:

- add `"[[<note>]]"` to `sources:` (if it isn't there already);
- add a line under `## Why sources point here`;
- recount `support`;
- set `updated:` to today;
- add a line at the top of `## Log`: `- YYYY-MM-DD — new support: [[<note>]]`;
- if the note adds a different way to do it, you may add one sentence about it to the paragraph under the title ("A later post suggests doing it with …").

For a learning, the line goes under `## What each source adds`, and the paragraph under the title is rewritten as the shared learning (see "Update first, create last"); its title may be sharpened only if the new source changes what the learning says, never just reworded.

Never change an idea's title, the slug, `created`, or `status`. Never remove a source. Never write in `## My notes`. If Marco has set `status: dropped`, still record the new support, but don't reword the idea.

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

- `## Learnings behind it` (optional, after `## Related ideas`): `- [[learning-…]]` for each learning this idea puts into practice.
- `status` belongs to Marco after creation. Agents write `new` and never change it. Values he may use: `new`, `trying`, `kept`, `dropped`.
- Omit `## Tensions` and `## Related ideas` when empty. Keep `## Log` and `## My notes` (empty) always.
- Tags: block list, lowercase with dashes, always `idea`; reuse topic tags from `commonplace.md`. Never write a `type/` tag (brain-index sets `type/inbox`).
- English throughout. Quotes from a source stay in their original language.

## Learning note format

```markdown
---
description: <one line, at most ~15 words: the learning and when to open the note>
created: YYYY-MM-DD
updated: YYYY-MM-DD
support: <number of independent sources>
sources:
  - "[[video-…]]"
status: new
tags:
  - learning
  - <1–2 topic tags from commonplace.md>
---

# <The learning, as one sentence>

> [!note] AI-generated learning drawn from the notes below. Not verified fact.

<2–4 lines: the shared learning, what the sources say together, and how strong the evidence is.>

## What each source adds

- [[video-a]] — <one line: what this source contributes: the claim, an example, a reason, a limit>

## Where they differ

- [[video-c]] — <one line: what it says against or beside it>

## Use it

- [[idea-…]]

## Related learnings

- [[learning-…]]

## Log

- YYYY-MM-DD — created from [[video-a]]

## My notes

```

- Counting sources, `status` (Marco's values: `new`, `kept`, `dropped`), tags (always `learning`), omitting empty sections (`## Where they differ`, `## Use it`, `## Related learnings`) and language follow the idea rules above.
- `## Use it` lists only existing ideas. If no idea applies the learning, leave the section out; never invent advice to fill it.

## Tone and honesty

- A learning reports what its sources claim and how well supported it is; it never upgrades an opinion or an anecdote into a fact.
- An idea's title is an action, but the body reports what the sources say: "Three posts recommend…", "The Jim Rohn talk suggests…". No advice of your own beyond what the sources say.
- If a source's note rated a related claim in its **Checked** section, carry the verdict over: "the '65% less anxiety' figure comes from a small commercial study (see the note)". Never present a disputed claim as fact.
- Keep it short. An idea or learning note is a pointer to its sources, not an essay.
- Never invent a source or a link. Every `[[link]]` must be an existing note: check with `find ~/Projects/brain -name "<name>.md"`.

## Migrating the first ideas

The 14 ideas from the first run (`Inbox/idea-*.md`) move into `Inbox/ideas/` with `git mv`, keeping their names, so links to them still work. Each gets the front matter above: `created` and `updated` from the commit that added it, `support: 1`, its one source in `sources:`, `status: new`, tag `idea` plus the topic tags of its source note. Its body becomes the paragraph under the title, followed by `## Why sources point here` with the source, `## Log` with `- <created> — created from [[video-…]] (first run, migrated <today>)`, and an empty `## My notes`. The wording of the old body is kept.
