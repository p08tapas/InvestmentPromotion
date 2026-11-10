from __future__ import annotations

import json
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx

NSE_HOME = "https://www.nseindia.com"
NSE_FILINGS_PAGE = f"{NSE_HOME}/companies-listing/corporate-filings-actions"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": NSE_FILINGS_PAGE,
}


def _fmt_nse_date(d: date) -> str:
    return d.strftime("%d-%m-%Y")


class NseClient:
    """NSE JSON client — warms cookies via the Corporate Filings page."""

    def __init__(self, *, min_interval_s: float = 0.35) -> None:
        self._min_interval_s = min_interval_s
        self._last_call = 0.0
        self._client = httpx.Client(
            timeout=90.0,
            follow_redirects=True,
            headers=dict(DEFAULT_HEADERS),
        )
        self._warmed = False

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> NseClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._min_interval_s:
            time.sleep(self._min_interval_s - elapsed)
        self._last_call = time.monotonic()

    def warm_up(self) -> None:
        if self._warmed:
            return
        self._throttle()
        self._client.get(NSE_FILINGS_PAGE)
        self._warmed = True

    def get_json(self, path: str, params: dict[str, str] | None = None) -> Any:
        self.warm_up()
        self._throttle()
        url = f"{NSE_HOME}{path}" if path.startswith("/") else path
        response = self._client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def corporate_announcements(
        self,
        from_date: date,
        to_date: date,
        *,
        index: str = "equities",
        subject: str | None = None,
    ) -> list[dict]:
        params: dict[str, str] = {
            "index": index,
            "from_date": _fmt_nse_date(from_date),
            "to_date": _fmt_nse_date(to_date),
        }
        if subject:
            params["subject"] = subject
        data = self.get_json("/api/corporate-announcements", params)
        return data if isinstance(data, list) else []

    def corporate_actions(self, from_date: date, to_date: date, *, index: str = "equities") -> list[dict]:
        data = self.get_json(
            "/api/corporates-corporateActions",
            {
                "index": index,
                "from_date": _fmt_nse_date(from_date),
                "to_date": _fmt_nse_date(to_date),
            },
        )
        return data if isinstance(data, list) else []

    def event_calendar(self, from_date: date, to_date: date, *, index: str = "equities") -> list[dict]:
        data = self.get_json(
            "/api/event-calendar",
            {
                "index": index,
                "from_date": _fmt_nse_date(from_date),
                "to_date": _fmt_nse_date(to_date),
            },
        )
        return data if isinstance(data, list) else []

    def annual_reports(self, symbol: str, *, index: str = "equities") -> list[dict]:
        data = self.get_json(
            "/api/annual-reports",
            {"index": index, "symbol": symbol.upper()},
        )
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            return data["data"]
        return []

    @staticmethod
    def load_subject_feeds(path: Path) -> list[dict[str, Any]]:
        if not path.is_file():
            return []
        return json.loads(path.read_text(encoding="utf-8")).get("equity_subjects", [])

    @staticmethod
    def default_sync_from_date(last_synced: date | None, *, fallback_days: int = 7) -> date:
        if last_synced:
            return last_synced + timedelta(days=1)
        return date.today() - timedelta(days=fallback_days)
