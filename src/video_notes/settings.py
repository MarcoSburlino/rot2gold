"""Validate editable preferences and save their overlay outside Git."""

import json
import math
import os
import tempfile

from .config import DATA

EDITABLE = [
    dict(section="notes", key="backend", label="AI backend", help="Use your Claude subscription or an API key.", type="choice", choices=("subscription", "api")),
    dict(section="notes", key="model", label="Notes model", help="Claude model for writing notes.", type="choice", choices=("opus", "sonnet", "haiku")),
    dict(section="notes", key="batch_size", label="Notes batch size", help="Posts per note-writing call.", type="int", min=1, max=20),
    dict(section="notes", key="max_per_run", label="Notes per run", help="Most notes to write in one Extract.", type="int", min=1, max=200),
    dict(section="notes", key="stop_at_plan_usage", label="Stop at plan usage", help="Stop before the next batch at this five-hour usage fraction.", type="float", min=0.5, max=1.0, step=0.01),
    dict(section="notes", key="max_budget_usd_per_batch", label="API budget per batch", help="API only; leave empty for no cap.", type="float", min=0.1, max=50, step=0.1, optional=True),
    dict(section="ideas", key="model", label="Ideas model", help="Claude model for the ideas pass.", type="choice", choices=("opus", "sonnet", "haiku")),
    dict(section="ideas", key="batch_size", label="Ideas batch size", help="Notes considered per ideas call.", type="int", min=5, max=50),
    dict(section="ideas", key="max_new_per_pass", label="New ideas per pass", help="Most new ideas in each batch.", type="int", min=1, max=20),
]


def path():
    return DATA / "settings.json"


def read() -> dict:
    try:
        value = json.loads(path().read_text())
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, ValueError, OSError):
        return {}


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
            elif field["type"] == "int":
                if isinstance(raw, bool) or str(raw).strip() != str(int(raw)):
                    raise ValueError("enter a whole number")
                value = int(raw)
            else:
                value = float(raw)
                if not math.isfinite(value):
                    raise ValueError("enter a finite number")
            if field["type"] != "choice" and not field["min"] <= value <= field["max"]:
                raise ValueError(f"enter a value from {field['min']} to {field['max']}")
            out.setdefault(section, {})[key] = value
        except (TypeError, ValueError) as exc:
            errors.append(f"{field['label']}: {exc}")
    if errors:
        return errors
    target = path()
    target.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=target.parent, prefix="settings-", suffix=".tmp", delete=False) as f:
            name = f.name
            json.dump(out, f, indent=2)
            f.write("\n")
        os.replace(name, target)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)
    return []
