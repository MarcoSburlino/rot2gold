"""The Anthropic API key, kept in the GNOME keyring through secret-tool.

The keyring is an encrypted store unlocked at login. The key is passed to secret-tool on stdin,
never as an argument (arguments are visible to every user in `ps`), and is never printed or logged.
"""

import shutil
import subprocess

from .errors import AgentFailed

ATTRS = ["service", "rot2gold", "account", "anthropic"]


def _tool() -> str:
    exe = shutil.which("secret-tool")
    if not exe:
        raise AgentFailed("keyring unavailable: secret-tool not found", "sudo dnf install libsecret")
    return exe


def get_api_key() -> str | None:
    proc = subprocess.run([_tool(), "lookup", *ATTRS], capture_output=True, text=True)
    if proc.returncode != 0 and proc.stderr.strip():
        raise AgentFailed("keyring unavailable", "Open the app from your desktop session, where the keyring is unlocked.")
    return proc.stdout.strip() or None


def has_api_key() -> bool:
    try:
        return bool(get_api_key())
    except AgentFailed:
        return False


def set_api_key(key: str) -> None:
    proc = subprocess.run([_tool(), "store", "--label=Rot2Gold Anthropic API key", *ATTRS],
                          input=key.strip(), capture_output=True, text=True)
    if proc.returncode != 0:
        raise AgentFailed("could not store the key in the keyring", proc.stderr.strip()[:200])


def delete_api_key() -> None:
    subprocess.run([_tool(), "clear", *ATTRS], capture_output=True, text=True)
