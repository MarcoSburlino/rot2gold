"""Platforms the pipeline can read. Add a Source subclass and register it here."""

from .base import Access, ListedPost, Source
from .tiktok import TikTokSource

SOURCES: dict[str, Source] = {s.platform: s for s in (TikTokSource(),)}


def get(platform: str) -> Source:
    try:
        return SOURCES[platform]
    except KeyError:
        raise ValueError(f"unknown platform {platform!r}; known: {', '.join(SOURCES)}") from None


__all__ = ["Access", "ListedPost", "Source", "SOURCES", "get"]
