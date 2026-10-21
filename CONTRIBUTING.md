# Contributing

Thanks for helping. Issues and pull requests are welcome.

## Set up a copy to work on

```sh
git clone https://github.com/MarcoSburlino/rot2gold
cd rot2gold
uv venv --python 3.14
uv pip install -e ".[dev]"
.venv/bin/r2g                     # Windows: .venv\Scripts\r2g
```

To keep a development copy apart from the one you use, give it its own config: `R2G_CONFIG=~/r2g-dev.toml .venv/bin/r2g` runs setup again with separate folders (pick another port under `[app]` if both run at once).

## Tests

```sh
.venv/bin/python -m pytest -q tests
```

They run on Linux, macOS and Windows in CI (`.github/workflows/test.yml`). `tests/browser/` drives the running app in Firefox with Selenium; see its README.

## Where things are

- `AGENTS.md`: the rules for working in this repository (read it first, people and AI agents alike).
- `src/rot2gold/`: the pipeline (sync, fetch, process), the AI providers (`ai/`, `direct.py`), vault writing (`brain.py`, `vault.py`), setup (`firstrun.py`) and the app (`web/`).
- `src/rot2gold/resources/`: what the AI is told (rules, prompts), note templates and the default settings.
- `.claude/skills/design-system/`: the visual design. UI changes follow it: always dark, one gold accent, bundled fonts, nothing loaded from other sites.
- `docs/`: the design log: decisions, data model and history.

## Please

- Keep personal data out: no real collection links, account names or API keys in code, tests or screenshots. Tests use made-up links.
- Never widen what the AI agents may run: transcripts are text from strangers.
- Keep the app working without JavaScript (plain links and forms), and keyboard-usable.
