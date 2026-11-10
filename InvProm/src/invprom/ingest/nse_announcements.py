"""Backward-compatible helpers; primary sync lives in nse_client.py and nse_sync.py."""

from __future__ import annotations

from datetime import date, timedelta

from invprom.ingest.nse_client import NseClient
from invprom.ingest.nse_tags import AnnouncementTag, tag_nse_text

__all__ = ["AnnouncementTag", "tag_announcement_title", "fetch_nse_announcement_titles"]


def tag_announcement_title(title: str) -> AnnouncementTag:
    tags = tag_nse_text(title)
    return AnnouncementTag(title=title, is_expansion=tags.is_expansion, mentions_odisha=tags.mentions_odisha)


def fetch_nse_announcement_titles(symbol: str, *, limit: int = 20) -> list[str]:
    titles: list[str] = []
    with NseClient() as client:
        to_date = date.today()
        from_date = to_date - timedelta(days=365)
        rows = client.corporate_announcements(from_date, to_date)
        for item in rows:
            if (item.get("symbol") or "").upper() != symbol.upper():
                continue
            text = item.get("attchmntText") or item.get("desc") or ""
            if text:
                titles.append(str(text))
            if len(titles) >= limit:
                break
    return titles
