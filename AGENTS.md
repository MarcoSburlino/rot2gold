# video-notes-app

Turns the posts Marco saves on TikTok into notes in his brain (`~/Projects/brain/Resources/commonplace/`), plus ideas found across notes (`~/Projects/brain/Inbox/ideas/`). The project name may change: mention it in as few places as possible.

Two parts, one repo:

- **The pipeline, `vn`** (built, working): lists a collection, downloads each post, runs OCR (Tesseract) and speech-to-text (faster-whisper), and stores everything in SQLite. An agent then writes one note per post.
- **The app** (Phase 1 built): a local web UI where Marco adds connections (collections), presses Extract, and the whole pipeline runs, including note writing; next come screens to browse posts and notes, and the ideas pass (`docs/app-spec.md` → "Phases").

## Docs

- `docs/spec.md`: the pipeline, its data and every decision, with test results.
- `docs/app-spec.md`: the app: goals, decisions and why, data model, Extract steps, screens, phases.
- `docs/note-writing.md`: how to write a note for a processed post. Follow it when asked to process posts.
- `docs/ideas.md`: rules for the ideas pass. Every agent and backend follows it.
- `prompts/`: the prompts the app gives `claude -p` (one note-writing batch, one ideas pass).

## Rules

- AI reasoning runs through Marco's Claude subscription (Claude Code, `claude -p`) by default. The app may also use an Anthropic API key, by Marco's choice in Settings (decided 2026-10-19; this exception is for this project only). No local LLMs; local utility models (speech-to-text, OCR) are fine.
- The API key lives only in the GNOME keyring (`secret-tool`, `service video-notes-app`, `account anthropic`). Never in a file, `config.toml`, Git, logs or notes. Never print it.
- Never fetch or store captions, hashtags or comments.
- Connection (collection) URLs live only in the database (`data/vn.sqlite`, `vn conn list`), never in Git.
- One pipeline run at a time: every command that runs the pipeline takes the lock `data/vn.lock`. Never delete the lock file by hand; the kernel releases it when its process ends.
- The web UI listens on `127.0.0.1:8740` only, never `0.0.0.0`.
- Brain writes follow `~/Projects/brain/AGENTS.md`: `brain-index` and `brain-index --check` after changes; commits start `agent: ` and stage only the paths that changed. Never `git add -A`, never `.obsidian/`, never push the brain.
- `data/` (media, database, tools) and `.venv/` are gitignored. Secrets never go into notes or Git.
- Fedora: `dnf`, not `apt`.

## How to run it

```
vn ui             # the app at http://127.0.0.1:8740 (Ctrl+C stops the server, not a running Extract)
vn extract        # the whole pipeline for every connection, as one run; --conn 1,2  --max-notes N  --no-notes
vn conn list      # connections; add <url> [--name N] | edit <id> | rm <id> | links <id> < urls.txt
vn runs           # recent runs with counts and AI usage
vn run 25         # sync + fetch + process up to 25 posts, without note writing
vn status         # counts by status and skip reason; connections; what is running
vn pending 10     # processed posts waiting for a note
vn done <id> <note-path>   |   vn skip <id> "<reason>"
.venv/bin/python -m pytest -q tests   # tests (temporary folders only; never the real database or brain)
```

- Setup:
  ```
  uv venv --python 3.14 .venv
  uv pip install --python .venv/bin/python -e '.[dev]'
  ln -sfn ~/Projects/video-notes-app/.venv/bin/vn ~/.local/bin/vn
  ```
  The venv records its own absolute path, so after moving or renaming this folder, delete `.venv` and run the setup again.
  Tesseract comes from `sudo dnf install tesseract tesseract-langpack-ita tesseract-langpack-spa` (fallback: `docs/spec.md`).
- When TikTok downloads start failing: `uv pip install --python .venv/bin/python -U 'yt-dlp[default,curl-cffi]' gallery-dl`.
- Every stage skips finished work. Stop any command and rerun it.
- Whisper model benchmark: `.venv/bin/python scripts/whisper_bench.py <out-dir> data/media/<id>/audio.wav ...`. Run it on fetched posts before `vn process`, which deletes the audio.

When asked to process posts, follow docs/note-writing.md.

## Brain

Project note: ~/Projects/brain/Projects/video-notes-app.md. Add a log entry there at the end of a session that changed something.
