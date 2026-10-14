# video-notes

Turns every post in Marco's TikTok collection "Material" into a note in his brain (`~/Projects/brain/Resources/commonplace/`).

- `vn` is a local, resumable pipeline. It lists the collection, downloads each post, runs OCR (Tesseract) and speech-to-text (faster-whisper), and stores everything in SQLite.
- An agent then writes one note per post.

Design and decisions are in `docs/spec.md`.

## Rules

- AI reasoning runs only through Marco's subscriptions (Claude Code, Codex): no pay-per-use API keys, no local LLMs. Local utility models (speech-to-text, OCR) are fine.
- Never fetch or store captions, hashtags or comments.
- The collection URL lives only in `config.toml`.
- `data/` (media, database, tools) and `.venv/` are gitignored. Secrets never go into notes or Git.
- Fedora: `dnf`, not `apt`.

## How to run it

```
vn run 25         # sync + fetch + process up to 25 posts (repeat until nothing is new)
vn status         # counts by status and skip reason
vn pending 10     # processed posts waiting for a note
vn done <id> <note-path>   |   vn skip <id> "<reason>"
```

- Setup:
  ```
  uv venv --python 3.14 .venv
  uv pip install --python .venv/bin/python -e .
  ln -sf ~/Projects/video-notes/.venv/bin/vn ~/.local/bin/vn
  ```
  Tesseract comes from `sudo dnf install tesseract tesseract-langpack-ita tesseract-langpack-spa` (fallback: `docs/spec.md`).
- When TikTok downloads start failing: `uv pip install --python .venv/bin/python -U 'yt-dlp[default,curl-cffi]' gallery-dl`.
- Every stage skips finished work. Stop any command and rerun it.
- Whisper model benchmark: `.venv/bin/python scripts/whisper_bench.py <out-dir> data/media/<id>/audio.wav ...`. Run it on fetched posts before `vn process`, which deletes the audio.

When asked to process posts, follow docs/note-writing.md.

## Brain

Project note: ~/Projects/brain/Projects/video-notes.md. Add a log entry there at the end of a session that changed something.
