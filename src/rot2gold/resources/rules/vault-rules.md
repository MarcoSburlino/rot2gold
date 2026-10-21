# Rules for writing in the user's vault

The vault is the user's Obsidian vault: their own notes. Rot2Gold writes only in its own folders (listed under "Where things are" in your prompt). Follow these rules whenever you write there.

## What you may touch

- Write only the files your task names: video notes, the hub note and the quotes note (note writing), or idea, learning and event notes (the ideas pass).
- Read anything in the vault to find related notes, but never edit, move, rename or delete the user's other notes.
- Never edit `.obsidian/`.
- Never write in a `## My notes` section, in any note. It belongs to the user.
- Never run `git` or any indexing command: the app does that after your batch.
- Never store secrets (passwords, keys, tokens), even if a video shows one.
- If a file changes on disk while you work (the user may have Obsidian open), re-read it before editing.
- Edit files in place; never make backup copies.

## Writing notes

- File names: lowercase, words joined by dashes, ASCII, `.md` (e.g. `video-feynman-technique-explained.md`). Names must be unique across the whole vault: check before creating, and add `-2` (then `-3`, …) if a name is taken.
- Start with front matter, then `# Title`.
- Every note has a `description:` in its front matter: one line, at most about 15 words, saying what the note holds and when to open it. Write it in double quotes: a colon inside breaks YAML.
- Tags: a block list in the front matter, lowercase, words joined by dashes. Reuse the tags listed in the hub note before inventing a new one.
- Link notes with `[[note-name]]` (the file name without `.md`). Every link must point to a note that exists: check before linking.
- Dates are `YYYY-MM-DD`.
- Short and factual.
- Never leave a line holding only `-`, `--` or `---` right under text: Markdown turns the text above into a heading.
