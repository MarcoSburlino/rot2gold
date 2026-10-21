"""Local models through an OpenAI-compatible server: Ollama, LM Studio or llama.cpp's llama-server.

A local model gets no tools: it can't read files, run `r2g` or search the web. So the app sends everything
the model needs in the prompt, asks for the answer as JSON (constrained by a schema), and writes the files
itself (see direct.py).
"""

import time

import httpx

from ..errors import AgentFailed
from .base import Result, json_from_text, strict

DEFAULT_URL = "http://localhost:11434/v1"  # Ollama; LM Studio uses :1234/v1


def _headers(api_key: str | None) -> dict:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def chat(prompt: str, *, schema: dict, model: str, url: str = DEFAULT_URL, api_key: str | None = None,
         system: str = "", timeout: float = 900) -> Result:
    """One request; the answer must match `schema`."""
    if not model:
        raise AgentFailed("No local model chosen", "Pick one in Settings → AI.")
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    body = {"model": model, "messages": messages, "temperature": 0.3, "stream": False,
            "response_format": {"type": "json_schema", "json_schema": {"name": "answer", "strict": True,
                                                                      "schema": strict(schema)}}}
    res, t0 = Result(), time.monotonic()
    try:
        r = httpx.post(url.rstrip("/") + "/chat/completions", json=body, headers=_headers(api_key), timeout=timeout)
    except httpx.HTTPError as exc:
        raise AgentFailed(f"Can't reach the local model server at {url}: {exc}",
                          "Start Ollama (or your server) and check the address in Settings → AI.") from None
    res.duration_ms = int((time.monotonic() - t0) * 1000)
    if r.status_code != 200:
        res.error = f"local model server answered {r.status_code}: {r.text[:300]}"
        return res
    data = r.json()
    u = data.get("usage") or {}
    res.usage = {"tokens_in": u.get("prompt_tokens", 0), "tokens_out": u.get("completion_tokens", 0),
                 "cache_read": 0, "cache_write": 0}
    res.turns = 1
    res.text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    res.structured = json_from_text(res.text)
    res.ok = res.structured is not None
    if not res.ok:
        res.error = "The local model's answer wasn't valid JSON: " + res.text[:300]
    return res


def models(url: str = DEFAULT_URL, api_key: str | None = None) -> list[str]:
    r = httpx.get(url.rstrip("/") + "/models", headers=_headers(api_key), timeout=10)
    r.raise_for_status()
    return sorted(m.get("id", "") for m in r.json().get("data", []) if m.get("id"))


def check(url: str = DEFAULT_URL, api_key: str | None = None) -> tuple[bool, str]:
    try:
        found = models(url, api_key)
    except httpx.HTTPStatusError as exc:
        return False, f"The server at {url} answered {exc.response.status_code}. Check the address and API key."
    except httpx.HTTPError:
        return False, f"No local model server at {url}. Install Ollama (ollama.com), start it, and pull a model."
    if not found:
        return False, f"The server at {url} has no models. Pull one first, e.g. `ollama pull qwen3:8b`."
    return True, f"{len(found)} models available: {', '.join(found[:5])}" + ("…" if len(found) > 5 else "")
