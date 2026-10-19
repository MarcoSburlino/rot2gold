# Writing notes for processed posts

Instructions for any agent (Claude Code, Codex) asked to process posts. `vn` has already downloaded each post and extracted its text (OCR) and speech (transcript). Your job is to turn each processed post into one note in Marco's brain.

Read the brain's rules first: `~/Projects/brain/AGENTS.md`, especially "Writing notes" and "Commonplace".

## Workflow

1. Get work: `vn pending 10` prints up to 10 posts waiting for a note: id, URL, creator, date, type, speech language, each image with its OCR text, confidence and path, and the transcript with timestamps. `vn pending --id <id>` shows one post; add `--json` for JSON.
2. For each post:
   1. Check whether a note already exists for it (an earlier run may have been stopped mid-post): `rg -l 'post_id: "<id>"' ~/Projects/brain/Resources/commonplace/videos`. If one exists, finish or replace that file instead of creating a new name.
   2. Read the OCR text, then check it against the image. **Always open a video's frame image** (one per video, cheap): frame OCR often misses small text or reads picture texture as words (in testing it read "1300" where the frame said "ARE"). **Open a slide image when its OCR confidence is below 85, its text looks garbled, or it seems to miss text.** The image is the source; OCR is only a draft.
   3. Search the brain for related notes: `rg -il "<term>" ~/Projects/brain`. Read `Resources/commonplace/commonplace.md` for the themes and topic tags in use.
   4. Write the note (format below), with web searches for the "Checked" claims.
   5. Update the hub and quotes (see "After each note").
   6. `vn done <id> Resources/commonplace/videos/video-<slug>.md`, or `vn skip <id> "<reason>"` if the content turns out to be useless (e.g. "music only; on-screen text is a single word"). Don't write a note for a skipped post.
3. After the batch, in `~/Projects/brain`. Skip this step when the app runs the batch (`vn extract` or the Extract button): the app indexes and commits.
   1. `brain-index`, then `brain-index --check` must exit 0.
   2. Commit by staging only the paths you changed, plus the regenerated indexes. Never `git add -A`; other agents may be working there:
      ```
      git -C ~/Projects/brain add Resources/commonplace Resources/resources-index.md index.md
      git -C ~/Projects/brain commit -m "agent: video notes batch"
      ```
      If brain-index retagged someone else's note, leave that note unstaged.
   3. The brain has no remote. Never add one, never push.

Never fetch or store a post's caption, hashtags or comments, not even from the web page while researching.

## Note format (one per post)

**Path:** `~/Projects/brain/Resources/commonplace/videos/video-<slug>.md`. The slug comes from the English title: lowercase, words joined by dashes, ASCII only, at most about 8 words. File names must be unique across the whole vault: check with `find ~/Projects/brain -name "video-<slug>.md"`. If the name is taken, add `-2` (then `-3`, …).

**Template:** `~/Projects/brain/System/templates/video-note.md`.

**Front matter:**

```yaml
---
description: <one line, at most ~15 words: what the post says and when to open the note>
source: <post URL>
creator: "@<creator>"
posted: YYYY-MM-DD
processed: <today, YYYY-MM-DD>
type: video            # or slideshow
language: en           # language of the Content section (ISO 639-1); "mixed" if more than one
post_id: "<id>"        # quoted, so it stays a string
tags:
  - tiktok
  - <1–3 topic tags>
---
```

- Tags go in a block list, lowercase with dashes. Never write a tag starting with `type/`; brain-index sets those.
- Reuse the topic tags listed in `commonplace.md` before inventing a new one. When you do create one, add it to that list.

**Sections, in this order:**

1. `# <Descriptive English title>`, then this callout, exactly:
   ```
   > [!note] AI-processed note. The Content section is the creator's words. Everything after it is AI-written and not verified fact unless a source says so.
   ```
2. `## Key points`: 3–5 neutral bullets in English summarising what the post says. Report, don't endorse: "The creator argues…", "The post claims…".
3. `## Content`, in the original language.
   - Video: `### On-screen text (0.5 s)` with the frame's text (or `No text.`), then `### Transcript` (or `No speech.` if there is none).
   - Slideshow: `### Slide 1`, `### Slide 2`, … with each image's text (`No text.` for an image without any).
   - Clean the text up: fix misheard words, OCR errors and misspelled names; remove filler ("um", false starts) and repetition; split into paragraphs. Drop timestamps.
   - Never add content, and never change the meaning or wording beyond those fixes. Don't translate, summarise or reorder.
   - Mark uncertain fixes with `[?]` right after the word, and unreadable or unintelligible parts with `[illegible]` or `[inaudible]`. A fix that restores grammar by changing a word (e.g. Whisper's "che" where the speaker likely said "è chi") is uncertain: mark it.
   - The only text you may add is a short italic label saying what a piece of on-screen text is, e.g. `*(Screenshot of a post by @AnthropicAI:)*`. Don't describe images otherwise; that belongs in Key points or Context.
   - Label speakers if there is more than one (`**Interviewer:**`, `**Speaker 2:**`, or the name if it is clear from the post).
   - On-screen text that only repeats the speech word for word (karaoke-style subtitles) is still written in the on-screen section, as it is.
4. `## References`, in two parts:
   - `**Mentioned**`: every person, book, study, event or work that is named or clearly paraphrased, with a link where useful (Wikipedia, the publisher, the paper). `None.` if there are none.
   - `**Checked**`: at most 3 factual claims that matter, verified with web search. These are statistics, studies, historical or scientific claims, what a politician, law or country did, and famous quotes (which are often misattributed). Format: `- <claim> — **supported | partly supported | disputed | not found**. <one line on what the sources say>. Sources: [name](url), [name](url)`. Use 1–2 good sources per claim. Don't check opinions, values, interpretations, advice or jokes. If nothing needs checking, write `No factual claims needing a check.`
5. `## Context and other perspectives`:
   - Factual background the post assumes or leaves out.
   - The main positions on the topic, each attributed to who holds it ("Supporters of X argue…, critics point to…"). On political topics, present them evenhandedly.
   - Related thinkers or ideas, and `Further reading:` with 1–3 suggestions.
   - `Related notes:` links to related notes already in the brain (`[[note-name]]`), found with `rg`. Omit the line if there are none.
6. `## Insights`: neutral observations only. What concept or debate the post is an example of, how it connects to other posts or notes in the brain, and patterns across the collection. No verdicts on whether the creator is right, no advice, no personal opinions: Marco asks for opinions himself in later sessions.
7. `## My notes`: left empty. This section belongs to Marco; agents never write in it, in any note.

Everything outside Content is in English.

## After each note

- **quotes.md**: add 1–3 standout lines from the Content (original language, verbatim from your cleaned text), at the bottom:
  `- "<line>" — @<creator>, [[video-<slug>]]`
  Skip this if nothing stands out.
- **Ideas**: don't write idea notes or touch `Inbox/`. Ideas are found across notes by a separate pass, with its own rules in `docs/ideas.md` (until 2026-10-19 each note writer added a one-source idea to `Inbox/` here).
- **commonplace.md**: list the post under its theme in `## Posts by theme`, as `- [[video-<slug>]] — <short description>` under a `### <Theme>` heading. Reuse an existing theme where it fits; themes are broad (e.g. "Philosophy and meaning", "Money and business", "AI and work"). Add any new topic tags to `## Topic tags in use`.
- Run `vn done <id> Resources/commonplace/videos/video-<slug>.md`.

## Working rules (learned on the first full run)

- Finish each post completely before starting the next: note, quotes, hub, `vn done`. If you are interrupted, nothing is left half-registered.
- Edit files in place; never make backup copies. Git tracks the brain.
- Many posts are quote slideshows from the same few accounts. Before checking a quote, `rg` the existing notes: if it was already checked, link that note and reuse its verdict.
- If you identify an unnamed speaker only by face or voice, say it is unconfirmed ("appears to be … [?]").
- If you do your own calculation in a note, say it is an AI calculation and state the assumption it rests on.
- Marco may have Obsidian open on the vault: if a file changes on disk, re-read it before editing.

## Quality bar

- Neutral tone throughout, including the title and key points. No praise, no debunking voice; let the "Checked" verdicts and attributed perspectives carry the evaluation.
- Content is cleaned, not rewritten: someone comparing it with the video should recognise every sentence.
- References are real and useful: link to sources you actually opened, never invented URLs.
