"""What every AI provider returns, and small helpers the providers share."""

import json
import re
from dataclasses import dataclass, field


@dataclass
class Result:
    ok: bool = False
    structured: dict | None = None
    text: str = ""
    error: str = ""
    turns: int = 0
    duration_ms: int = 0
    cost_usd: float = 0.0
    usage: dict = field(default_factory=lambda: {"tokens_in": 0, "tokens_out": 0, "cache_read": 0, "cache_write": 0})
    plan: dict | None = None  # Claude only: latest rate_limit_info (five_hour / seven_day utilization, reset times)
    limited: bool = False
    other_output: list = field(default_factory=list)  # non-JSON lines (stderr), kept for errors


LIMIT_WORDS = ("usage limit", "hit your limit", "rate limit", "rate_limit", "quota", "resource_exhausted", "429")


def is_limit(message: str) -> bool:
    return any(w in message.lower() for w in LIMIT_WORDS)


def strict(schema: dict) -> dict:
    """A copy of a JSON schema in the strict form OpenAI requires: every object closed, every property required.
    Optional values are expressed as nullable types instead."""
    if not isinstance(schema, dict):
        return schema
    out = {k: strict(v) if isinstance(v, dict) else v for k, v in schema.items()}
    if "properties" in out:
        out["properties"] = {k: strict(v) for k, v in out["properties"].items()}
        out["required"] = list(out["properties"])
        out["additionalProperties"] = False
    if isinstance(out.get("items"), dict):
        out["items"] = strict(out["items"])
    return out


def json_from_text(text: str) -> dict | None:
    """The JSON object an agent ended its answer with: the whole text, the last ```json block,
    or the last {...} that parses."""
    text = (text or "").strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except ValueError:
        pass
    for block in reversed(re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)):
        try:
            return json.loads(block)
        except ValueError:
            continue
    end = text.rfind("}")
    start = text.rfind("{", 0, end)
    while start != -1 and end != -1:
        try:
            value = json.loads(text[start:end + 1])
            if isinstance(value, dict):
                return value
        except ValueError:
            pass
        start = text.rfind("{", 0, start)
    return None


def missing(value: dict | None, schema: dict) -> list[str]:
    """Top-level keys the schema requires that `value` lacks."""
    return [k for k in schema.get("required", []) if not isinstance(value, dict) or k not in value]
