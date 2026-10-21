# The ideas, learnings and events pass

Rules for finding ideas, learnings and events across the user's video notes and writing them as notes in their vault. Every AI provider follows this file, so ideas come out the same way each time.

Read the vault rules first (`vault-rules.md`, next to this file), and the user's own rules file if your prompt names one. The folder and file names below ("the ideas folder", "the hub note", …) are listed with their real paths under "Where things are" in your prompt.

## What an idea is

An idea is **a concrete thing the user could do**: a practice to try, a method, a tool, a book to read, a project or business idea. It is written as an action ("Try the Feynman technique on the next topic I study"), not as a topic ("Learning").

Its value comes from its **sources**: the notes that point to it. An idea that several independent sources point toward is stronger than an idea from one post.

What is *not* an idea: a quote, an opinion to agree with, a fact, a general theme ("stoicism"), or a purchase someone is promoting.

## What a learning is

A learning is **something understood about how things work**: a principle, a mechanism, a pattern or a finding that a video teaches. It is written as one sentence that states it ("Explaining a topic out loud shows the gaps that rereading hides"), not as a topic ("Learning techniques") and not as an action (that is an idea).

Learnings answer: what did a video teach, does another video say something related, and how do the sources combine into **one shared learning**. So a learning note is written to grow: the first video gives it, later videos that say the same thing (or add evidence, a reason, a limit) are added to it, and its paragraph is rewritten as what the sources say together.

- A learning may come from **one source** (`support: 1`). It is not a copy of that video's Key points or Insights: it is the one reusable lesson, phrased so another video could support it.
- What is *not* a learning: a bare quote, a motivational slogan with no claim in it, a fact about the video itself ("the creator uses subtitles"), or a claim the note's **Checked** section found false. A disputed claim can be a learning only if the note says so in the text ("a small commercial study claims…").
- **Ideas and learnings link up.** When an idea puts a learning into practice, the learning lists it under `## Use it` and the idea lists the learning under `## Learnings behind it`. A note can give an idea, a learning, both, or neither.

## What an event is

An event is **a specific happening with a time**, that a video reports or announces. Both kinds count:

- **What happened**: news (a strike, an election, a court ruling, a disaster), a release or launch (a product, an AI model, a book, a film), a historical event (a 1983 CIA report, a battle).
- **What is coming**: something the user could go to or watch: a conference, a festival, an exhibition, a concert, a match, a launch date, a deadline.

Its title names the event as a short noun phrase ("Yandex data-centre strikes", "Qwen 3.8 release", "Milan Design Week 2027"), not a sentence. One note per event, which grows as other videos talk about it.

- What is *not* an event: a trend ("AI is getting cheaper"), a habit or a recurring advice ("every spring, plan your year"), a person's life in general, the creator's own story with no public happening in it, the video itself, a sale or promotion someone is selling.
- A note can give an event and also a learning or an idea. The event is what happened; the learning is what it teaches ("viral claims spread because they confirm what people already believe"). When an event shows a learning, the event lists it under `## Learnings it shows` and the learning lists the event under `## Events that show it`.
- **Dates are never guessed.** `when:` is the first day as the note gives it (`YYYY-MM-DD`). If the video says "next Friday" or "this weekend", work it out from the note's `posted:` date and say so in the text. If only the month or the year is known, write `YYYY-MM` or `YYYY`. If there is no date at all, leave `when:` empty. `until:` is the last day of an event that lasts several days. `where:` is the place as the video gives it (`online` for a stream), or empty.
- The app sorts events by date: **Coming up** until their last day has passed, then **Past**. An event known only by its month or year counts as coming up only until that month or year begins. So a date must be right or left out, never invented.

## When the pass runs

One pass looks for all three kinds, in the same AI call per batch. The app records three checks per note (ideas, learnings, events). The prompt tags each note with what it still needs: `[ideas, learnings and events]`, `[learnings and events]`, `[events]`, and so on.

- **Inside each Extract**, right after its notes are written and committed: the same run, not a separate step. Input: notes not checked for ideas and finished on or after `[ideas] since`, then notes of **any age** not checked for learnings or events, in batches, carrying on next time when a limit stops the run.
- **"Rebuild ideas"**, started by hand from the app or CLI. Input: notes missing a check, under the themes the user selects in the hub note, regardless of date. Marking only considered notes lets a stopped rebuild resume.
- **Dry runs** write previews to a folder your prompt names, without marking posts or changing the vault.

The app gives the agent the list of notes to consider. The agent only writes idea, learning and event notes; the app runs any indexing, commits, and records which posts were considered.

## Where they live

- Ideas: `<ideas folder>/idea-<slug>.md`, template `idea-note.md` in the templates folder.
- Learnings: `<learnings folder>/learning-<slug>.md`, template `learning-note.md`.
- Events: `<events folder>/event-<slug>.md`, template `event-note.md`. Add the year to the slug of an event that repeats (`event-milan-design-week-2027`).
- The slug comes from the title: lowercase, words joined by dashes, ASCII, at most about 8 words. Names must be unique across the whole vault: check before creating, and add `-2` if taken.

## Update first, create last

The goal is **a few ideas that grow** as more videos point to them, not a new idea at every Extract. So in every pass:

- A note that **fits an existing idea updates it**. It fits when it supports the same goal or practice, even from a different angle, with a different method to reach the same thing, or as a narrower or broader version of it. "Explain a topic out loud to find the gaps" fits "Try the Feynman technique"; another clip about writing down long-term goals fits "Write a five-year plan"; a different speaker making the same point fits.
- If several existing ideas fit, update only the **closest** one (the same action first, then the same goal).
- A **dropped** idea still counts: a note that fits it records its support there and never creates a near-copy.
- **Create a new idea only when no existing idea fits**: the note points to a different action, one where doing it would not mostly mean doing an existing idea.
- Notes in the same pass that point to the same new action become **one** new idea with several sources.

The prompt lists every existing idea, learning and event (file, title, description, status, sources, and an event's date), so each candidate is compared with all of them before anything is created.

**Learnings follow the same rules.** A note that says the same thing as an existing learning, from another angle, with other evidence, or as a narrower or broader case, updates the closest learning. Create a new learning only when none fits. When a second source joins a learning, rewrite its paragraph as the **shared learning**: what the sources agree on, what each adds, and how strong the evidence is (a study, a personal story, an opinion). A source that says the opposite goes under `## Where they differ`.

**Events too.** A note about the same happening (the same thing, at the same time and place) updates that event, even if it calls it by another name or tells it from another side. A follow-up that is a happening of its own (a court ruling after a strike, the 2028 edition of a festival) is a new event, linked under `## Related events` in both. When sources give different dates, places or figures, keep the best-supported one in the front matter and list the others under `## Where they differ`.

## Steps

1. **Read what exists.** Start from the list of existing ideas in the prompt; open an idea's full note when a candidate might fit it.
2. **Read the notes to consider**, one at a time. For each, ask: does it contain a concrete action (see "What an idea is")? Note it as a candidate with the note as its source. Most notes have none; that is normal.
3. **Look for support** for each candidate:
   - older video notes: the hub note (themes and tags), then `rg -il "<term>" <videos folder>`;
   - the rest of the vault: `rg -il "<term>" <vault>`. A note of the user's that already does or plans something similar counts;
   - never read outside the vault and the folders your prompt names.
4. **Match before creating** (see "Update first, create last"). For each candidate, find the existing idea it fits best.
   - **Fits → update** that idea (below). Never create a second note for it.
   - **Nothing fits → it may become a new idea** (step 5). If it is related to an existing idea without fitting it, link the two under `## Related ideas` in both.
5. **Decide whether to create.** Only for candidates that fit no existing idea or learning. A learning or an event may be created from one source, up to the limits on new learnings and events in your prompt, with the same hold-back rule as ideas below. Create a new idea when:
   - **two or more independent sources** point to it, or
   - **one source** describes a clearly actionable practice, tool, book or project idea. It gets `support: 1` and ranks below multi-source ideas.
   - At most the number of new ideas your prompt allows. If there are more candidates, keep the best-supported ones, and leave the notes behind the others out of the reported `considered` list, so the next pass sees them again.
6. **Write or update** the notes (format below).
7. **Report** in the JSON format the prompt asks for: created files and updated files (all kinds together; the app tells them apart by the `idea-`/`learning-`/`event-` prefix), every post id you considered (including those that gave nothing), and in `notes` one line per considered note saying what it led to: `<post id> → updated idea-…; new learning-… (no existing learning fits: <why>)`, or `<post id> → nothing`.

## Counting sources

- `support` is the number of **independent** sources in `sources:`.
- Each note is one source. A video note and any other note in the vault are both sources.
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

Never change an idea's title, the slug, `created`, or `status`. Never remove a source. Never write in `## My notes`. If the user has set `status: dropped`, still record the new support, but don't reword the idea.

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
  - <1–2 topic tags from the hub note>
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
- `status` belongs to the user after creation. Write `new` and never change it. Values they may use: `new`, `trying`, `kept`, `dropped`.
- Omit `## Tensions` and `## Related ideas` when empty. Keep `## Log` and `## My notes` (empty) always.
- Tags: block list, lowercase with dashes, always `idea`; reuse topic tags from the hub note.
- Written in the note language named in your prompt. Quotes from a source stay in their original language.

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
  - <1–2 topic tags from the hub note>
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

## Events that show it

- [[event-…]]

## Related learnings

- [[learning-…]]

## Log

- YYYY-MM-DD — created from [[video-a]]

## My notes

```

- Counting sources, `status` (the user's values: `new`, `kept`, `dropped`), tags (always `learning`), omitting empty sections (`## Where they differ`, `## Use it`, `## Related learnings`) and language follow the idea rules above.
- `## Use it` lists only existing ideas. If no idea applies the learning, leave the section out; never invent advice to fill it.
- `## Events that show it` (optional) lists the events that illustrate the learning.

## Event note format

```markdown
---
description: <one line, at most ~15 words: the event, when and where, and when to open the note>
created: YYYY-MM-DD
updated: YYYY-MM-DD
when: YYYY-MM-DD          # first day; YYYY-MM or YYYY if that is all that is known; empty if unknown
until: YYYY-MM-DD         # last day, only for an event of several days
where: <place as the video gives it, or "online"; empty if unknown>
support: <number of independent sources>
sources:
  - "[[video-…]]"
status: new
tags:
  - event
  - <1–2 topic tags from the hub note>
---

# <The event, as a short noun phrase>

> [!note] AI-generated event note drawn from the videos below. Dates, places and figures are not verified: check them before relying on them.

<2–4 lines: what happened or will happen, who is involved, and why the videos talk about it.>

## What each source says

- [[video-a]] — <one line: what this source reports or claims about it>

## Where they differ

- [[video-c]] — <one line: a different date, figure or account>

## Learnings it shows

- [[learning-…]]

## Related events

- [[event-…]]

## Log

- YYYY-MM-DD — created from [[video-a]]

## My notes

```

- `status` (the user's values: `new`, `going` for something they plan to attend or watch, `kept`, `dropped`), counting sources, tags (always `event`), omitting empty sections (`## Where they differ`, `## Learnings it shows`, `## Related events`) and language follow the idea rules above.
- When a new source joins, update `updated:`, `support`, the source line and the Log as for an idea; correct `when:`, `until:` or `where:` only when the new source is better supported, and log it (`- YYYY-MM-DD — date corrected from [[video-b]]`).

## Tone and honesty

- A learning reports what its sources claim and how well supported it is; it never upgrades an opinion or an anecdote into a fact.
- An event reports what the videos say happened, and carries over the note's checks: "the note's sources confirm the strikes; the bot claim is disputed". A figure or a cause that only the video gives is attributed to it ("the video says…").
- An idea's title is an action, but the body reports what the sources say: "Three posts recommend…", "The Jim Rohn talk suggests…". No advice of your own beyond what the sources say.
- If a source's note rated a related claim in its **Checked** section, carry the verdict over: "the '65% less anxiety' figure comes from a small commercial study (see the note)". Never present a disputed claim as fact.
- Keep it short. An idea or learning note is a pointer to its sources, not an essay.
- Never invent a source or a link. Every `[[link]]` must be an existing note: check before linking.
