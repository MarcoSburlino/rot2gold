"""The AI providers. Claude Code, Codex CLI and Gemini CLI run as agents that write the notes themselves;
a local model runs in direct mode, where it answers in JSON and the app writes the notes (direct.py)."""

from .. import secrets
from . import claude_cli, codex_cli, gemini_cli, local
from .base import Result

PROVIDERS = {"claude": "Claude Code", "codex": "OpenAI Codex CLI", "gemini": "Google Gemini CLI",
             "local": "Local model (Ollama, LM Studio, llama.cpp)"}
AGENTS = {"claude": claude_cli, "codex": codex_cli, "gemini": gemini_cli}
# Keychain entry for each provider's optional API key.
KEY_ACCOUNTS = {"claude": "anthropic", "codex": "openai", "gemini": "gemini", "local": "local"}
# Model names offered in Settings; empty means the provider's own default.
MODELS = {"claude": ("", "opus", "sonnet", "haiku"), "codex": ("",), "gemini": ("", "pro", "flash", "flash-lite"),
          "local": ()}

__all__ = ["PROVIDERS", "Result", "api_key", "check", "is_direct", "provider", "run_agent"]


def provider(cfg: dict) -> str:
    return (cfg.get("ai") or {}).get("provider") or "claude"


def is_direct(cfg: dict) -> bool:
    return provider(cfg) == "local"


def run_label(cfg: dict) -> str:
    """How a run records its AI: Claude's account kind ("subscription" or "api"), or the provider."""
    name = provider(cfg)
    return cfg["notes"]["backend"] if name == "claude" else name


def api_key(cfg: dict) -> str | None:
    """The key to pass to the provider: Claude's only on its "api" backend; for the others, if one is saved."""
    name = provider(cfg)
    if name == "claude" and cfg["notes"]["backend"] != "api":
        return None
    return secrets.get_key(KEY_ACCOUNTS[name])


def run_agent(cfg: dict, prompt: str, *, schema: dict, cwd: str, add_dirs: list[str], model: str, on_line,
              api_key: str | None = None) -> Result:
    name = provider(cfg)
    if name == "claude":
        return claude_cli.run(prompt, schema=schema, cwd=cwd, add_dirs=add_dirs, model=model,
                              backend=cfg["notes"]["backend"], api_key=api_key,
                              max_budget_usd=cfg["notes"].get("max_budget_usd_per_batch"), on_line=on_line)
    return AGENTS[name].run(prompt, schema=schema, cwd=cwd, add_dirs=add_dirs, model=model, api_key=api_key,
                            on_line=on_line)


def check(cfg: dict) -> tuple[bool, str]:
    """Is the chosen provider installed and signed in? A short answer for Settings and setup."""
    name = provider(cfg)
    if name == "claude":
        import shutil
        if not shutil.which("claude"):
            return False, "Claude Code is not installed. Install it (claude.com/claude-code) and sign in by running `claude` once."
        if cfg["notes"]["backend"] == "api" and not secrets.has_key("anthropic"):
            return False, "Claude Code is installed, but no Anthropic API key is saved."
        return True, "Claude Code is installed."
    if name == "codex":
        return codex_cli.check()
    if name == "gemini":
        return gemini_cli.check(secrets.get_key("gemini") if secrets.has_key("gemini") else None)
    return local.check(cfg["ai"]["local_url"], secrets.get_key("local") if secrets.has_key("local") else None)
