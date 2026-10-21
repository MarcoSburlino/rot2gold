# The ideas, learnings and events pass

The rules the AI follows now ship with the app: `src/rot2gold/resources/rules/ideas.md` (with `vault-rules.md` beside it), and the prompt is `src/rot2gold/resources/prompts/ideas.md`. They speak of "the ideas folder", "the hub note" and so on; each prompt lists the real paths from the user's `[vault]` settings (`vault.where()`). Edit the rules there, not here.

This page keeps the project's history of the pass.

- 2026-10-19: the per-post idea step was replaced by one pass across notes (below).
- 2026-10-20: learnings and events were added (Marco's requests), and "update first, create last" so ideas grow instead of multiplying.
- 2026-10-21: the rules were made generic for the open-source release. Marco's brain keeps its layout through his `config.toml` (`Inbox/ideas`, `Inbox/learnings`, `Inbox/events`, templates in `System/templates`, his `AGENTS.md` as extra rules); the dates and choices that were his (Rebuild themes: Mindset and self-help, Learning and memory, Money and business; `[ideas] since = 2026-10-19`) are recorded here and in the brain note.

## History

On the first full run (2026-10-15), each batch agent decided per post whether it held "an idea Marco could act on", and if so wrote `Inbox/idea-<slug>.md`: a title as an action, 1–3 lines, and `From [[video-<slug>]].` That made 15 ideas, each with exactly one source; one was later archived. The video notes themselves linked to each other a lot (Related notes, Insights), but no step looked across notes for shared ideas.

This file replaces that per-post step with one pass that looks across sources. It keeps the old format's spirit: a short action title, a few lines of why, and links to where it came from.

## Migrating the first ideas

The 14 ideas from the first run (`Inbox/idea-*.md`) move into `Inbox/ideas/` with `git mv`, keeping their names, so links to them still work. Each gets the front matter above: `created` and `updated` from the commit that added it, `support: 1`, its one source in `sources:`, `status: new`, tag `idea` plus the topic tags of its source note. Its body becomes the paragraph under the title, followed by `## Why sources point here` with the source, `## Log` with `- <created> — created from [[video-…]] (first run, migrated <today>)`, and an empty `## My notes`. The wording of the old body is kept.
