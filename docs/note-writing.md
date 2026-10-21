# Writing notes for processed posts

The instructions the AI follows now ship with the app: `src/rot2gold/resources/rules/note-writing.md` (with `vault-rules.md` beside it), the prompt is `src/rot2gold/resources/prompts/write-notes.md`, and the note templates are in `src/rot2gold/resources/templates/` (copied into the user's vault by `vault.prepare()`, never over the user's own). Edit the rules there, not here.

History:

- 2026-10-15: first full run, written by hand-run agents from this file.
- 2026-10-19: the app took over indexing and committing; ideas moved to their own pass (`docs/ideas.md`).
- 2026-10-21: the rules were made generic for the open-source release: "the videos folder", "the hub note" and "the quotes note" instead of `Resources/commonplace/…`, a note language setting (`[notes] language`), and an invented example note (`resources/examples/`) instead of two of Marco's notes. Marco's `config.toml` still points the AI at his own two example notes (`[notes] examples`) and his brain's `AGENTS.md` (`[vault] rules`).
