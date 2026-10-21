"""API keys for the AI providers, kept in the system keychain through the `keyring` library:
the Secret Service (GNOME Keyring, KWallet) on Linux, Keychain on macOS, Credential Manager on Windows.

Keys never go in a file, a config, Git, logs or notes, and are never printed. Each provider has its own
entry: service "rot2gold", user "anthropic", "openai", "gemini" or "local".
"""

import keyring
from keyring.errors import KeyringError

from .errors import AgentFailed

SERVICE = "rot2gold"


def get_key(account: str) -> str | None:
    try:
        return keyring.get_password(SERVICE, account) or None
    except KeyringError as exc:
        raise AgentFailed(f"keychain unavailable: {exc}", "Open the app from your desktop session, where the keychain is unlocked.") from None


def has_key(account: str) -> bool:
    try:
        return bool(get_key(account))
    except AgentFailed:
        return False


def set_key(account: str, key: str) -> None:
    try:
        keyring.set_password(SERVICE, account, key.strip())
    except KeyringError as exc:
        raise AgentFailed("could not store the key in the keychain", str(exc)[:200]) from None


def delete_key(account: str) -> None:
    try:
        keyring.delete_password(SERVICE, account)
    except keyring.errors.PasswordDeleteError:
        pass  # nothing stored
    except KeyringError as exc:
        raise AgentFailed("could not remove the key from the keychain", str(exc)[:200]) from None


# The Anthropic key, used by Claude Code's "api" backend.
def get_api_key() -> str | None:
    return get_key("anthropic")


def has_api_key() -> bool:
    return has_key("anthropic")


def set_api_key(key: str) -> None:
    set_key("anthropic", key)


def delete_api_key() -> None:
    delete_key("anthropic")
