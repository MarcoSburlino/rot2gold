"""Validate editable preferences and save them into the user's config.toml."""

import math

from . import config

EDITABLE = [
    dict(section="ai", key="provider", label="AI", help="Who writes the notes. Claude Code, Codex and Gemini CLI work as agents (with web search); a local model is free and private, with simpler notes.", type="choice", choices=("claude", "codex", "gemini", "local")),
    dict(section="notes", key="model", label="Notes model", help="Empty uses the provider's default. Claude: opus, sonnet or haiku; Gemini: pro or flash; local: a model on your server.", type="text"),
    dict(section="ideas", key="model", label="Ideas model", help="The model that finds ideas, learnings and events. Empty uses the provider's default.", type="text"),
    dict(section="notes", key="backend", label="Claude account", help="Claude only: your Claude subscription, or an Anthropic API key.", type="choice", choices=("subscription", "api")),
    dict(section="notes", key="max_per_run", label="Notes per run", help="Most notes to write in one Extract.", type="int", min=1, max=200),
    dict(section="notes", key="language", label="Note language", help="The language notes are written in. The creator's words stay in theirs.", type="text"),
    dict(section="ai", key="local_url", label="Local server", help="Local models only: the address of an OpenAI-compatible server. Ollama: http://localhost:11434/v1; LM Studio: http://localhost:1234/v1.", type="url"),
    dict(section="notes", key="batch_size", label="Notes batch size", help="Posts per note-writing call.", type="int", min=1, max=20),
    dict(section="notes", key="stop_at_plan_usage", label="Stop at plan usage", help="Claude subscription: stop before the next batch at this five-hour usage fraction.", type="float", min=0.5, max=1.0, step=0.01),
    dict(section="notes", key="max_budget_usd_per_batch", label="API budget per batch", help="Claude API key only; leave empty for no cap.", type="float", min=0.1, max=50, step=0.1, optional=True),
    dict(section="ideas", key="batch_size", label="Ideas batch size", help="Notes considered per call that looks for ideas, learnings and events.", type="int", min=5, max=50),
    dict(section="ideas", key="max_new_per_pass", label="New ideas per pass", help="Most new ideas in each batch.", type="int", min=1, max=20),
    dict(section="ideas", key="max_new_learnings_per_pass", label="New learnings per pass", help="Most new learnings in each batch.", type="int", min=1, max=20),
    dict(section="ideas", key="max_new_events_per_pass", label="New events per pass", help="Most new events in each batch.", type="int", min=1, max=20),
]


def save(values: dict) -> list[str]:
    """Accept a nested mapping or form-style dotted names; save only after all values validate."""
    out, errors = {}, []
    for field in EDITABLE:
        section, key = field["section"], field["key"]
        raw = values.get(f"{section}.{key}", values.get(section, {}).get(key) if isinstance(values.get(section), dict) else None)
        if raw is None:
            continue
        if field.get("optional") and str(raw).strip() == "":
            out.setdefault(section, {})[key] = None
            continue
        try:
            if field["type"] == "choice":
                if raw not in field["choices"]:
                    raise ValueError(f"choose {', '.join(field['choices'])}")
                value = raw
            elif field["type"] in ("text", "url"):
                value = str(raw).strip()
                if len(value) > 200 or any(c in value for c in "\r\n\t"):
                    raise ValueError("enter one short line")
                if field["type"] == "url" and not value.startswith(("http://", "https://")):
                    raise ValueError("enter an address starting with http:// or https://")
            elif field["type"] == "int":
                if isinstance(raw, bool) or str(raw).strip() != str(int(raw)):
                    raise ValueError("enter a whole number")
                value = int(raw)
            else:
                value = float(raw)
                if not math.isfinite(value):
                    raise ValueError("enter a finite number")
            if field["type"] in ("int", "float") and not field["min"] <= value <= field["max"]:
                raise ValueError(f"enter a value from {field['min']} to {field['max']}")
            out.setdefault(section, {})[key] = value
        except (TypeError, ValueError) as exc:
            errors.append(f"{field['label']}: {exc}")
    if errors:
        return errors
    user = config.read_user()
    for section, values in out.items():
        for key, value in values.items():
            if value is None:  # TOML has no "empty": leaving the key out means no cap
                user.get(section, {}).pop(key, None)
            else:
                user.setdefault(section, {})[key] = value
    config.write_user(user)
    return []
