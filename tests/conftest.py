"""Point the app at a throwaway config before any test imports it, so tests never read the user's own.

The vault layout here is the one the tests were written for (folders spread over the vault);
test_setup.py covers the default single-folder layout.
"""

import os
import tempfile
from pathlib import Path

import tomli_w

_tmp = Path(tempfile.mkdtemp(prefix="r2g-tests-"))
os.environ["R2G_CONFIG"] = str(_tmp / "config.toml")
(_tmp / "config.toml").write_text(tomli_w.dumps({
    "vault": {"path": str(_tmp / "vault"), "videos": "Resources/commonplace/videos",
              "hub": "Resources/commonplace/commonplace.md", "quotes": "Resources/commonplace/quotes.md",
              "ideas": "Inbox/ideas", "learnings": "Inbox/learnings", "events": "Inbox/events",
              "templates": "System/templates", "git": "on", "after_write": [["brain-index"]],
              "commit_also": ["index.md", "Resources/resources-index.md", "Inbox/inbox-index.md"]},
    "storage": {"data_dir": str(_tmp / "data")},
}))


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_config():
    """A test that saves Settings writes the shared config; put it back afterwards."""
    text = (_tmp / "config.toml").read_text()
    yield
    (_tmp / "config.toml").write_text(text)
