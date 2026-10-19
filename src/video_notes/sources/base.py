"""What every platform provides. Sync, fetch and the app only talk to this interface."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ListedPost:
    id: str                 # bare id for TikTok; "<platform>:<id>" for other platforms
    url: str
    creator: str | None = None
    upload_date: str | None = None  # YYYY-MM-DD


@dataclass
class Access:
    """How to reach the platform for one connection."""
    cookies: bool = False
    firefox_profile: str | None = None  # None = let the downloader pick


class Source:
    platform = ""
    label = ""
    url_hint = ""

    def validate_url(self, url: str) -> str:
        """Return the URL cleaned up, or raise ValueError with a readable message."""
        raise NotImplementedError

    def default_name(self, url: str) -> str:
        return ""

    def list_posts(self, url: str, access: Access) -> list[ListedPost]:
        raise NotImplementedError

    def parse_post_url(self, line: str) -> ListedPost | None:
        raise NotImplementedError

    def detect_type(self, post_url: str, access: Access) -> tuple[str, dict]:
        """('video' | 'slideshow', metadata with optional creator and upload_date)."""
        raise NotImplementedError

    def fetch(self, post_id: str, post_url: str, kind: str, out: Path, cfg: dict,
              access: Access) -> list[tuple[str, Path]]:
        """Download into `out`; return images as (kind, path), with kind 'frame' or 'slide' in order."""
        raise NotImplementedError
