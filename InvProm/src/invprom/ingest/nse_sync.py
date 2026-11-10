from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import func
from sqlalchemy.orm import Session

from invprom.config import settings
from invprom.db.models import (
    Company,
    FinancialPeriod,
    NseAnnouncement,
    NseAnnualReport,
    NseCorporateAction,
    NseEvent,
    NseSyncState,
)
from invprom.ingest.nse_index_csv import sync_nse_index_classifiers
from invprom.ingest.nse_universe import refresh_listed_equity_names, sync_listed_equities, touch_listed_equity
from invprom.ingest.nse_client import NseClient
from invprom.ingest.nse_filing_classifier import (
    ANNUAL_REPORT,
    refine_filing_type,
    filing_type_from_nse_desc,
)
from invprom.ingest.nse_tags import tag_nse_text

FeedType = Literal[
    "corporate_filings",
    "all_announcements",
    "annual_reports",
    "corporate_actions",
    "events",
]


@dataclass
class SyncResult:
    feed: str
    from_date: date | None
    to_date: date | None
    fetched: int
    inserted: int
    updated: int
    detail: str | None = None


def _parse_sort_date(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d-%b-%Y %H:%M:%S"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def _get_sync_cursor(db: Session, feed: str) -> date | None:
    row = db.query(NseSyncState).filter(NseSyncState.feed == feed).one_or_none()
    return row.last_to_date if row else None


def _set_sync_cursor(db: Session, feed: str, to_date: date) -> None:
    row = db.query(NseSyncState).filter(NseSyncState.feed == feed).one_or_none()
    if row is None:
        row = NseSyncState(feed=feed, last_to_date=to_date)
        db.add(row)
    else:
        row.last_to_date = max(row.last_to_date, to_date)
        row.updated_at = datetime.utcnow()
    db.commit()


def _date_chunks(start: date, end: date, *, chunk_days: int = 1) -> list[tuple[date, date]]:
    chunks: list[tuple[date, date]] = []
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=chunk_days - 1), end)
        chunks.append((cur, chunk_end))
        cur = chunk_end + timedelta(days=1)
    return chunks


def _apply_tags_to_row(existing: NseAnnouncement, tags: Any, filing_type: str) -> None:
    existing.filing_type = filing_type
    existing.is_expansion = tags.is_expansion
    existing.mentions_odisha = tags.mentions_odisha
    existing.is_management_guidance = tags.is_management_guidance
    existing.is_ipicol_relevant = tags.is_ipicol_relevant
    existing.is_financial_results = tags.themes.is_financial_results
    existing.theme_new_plant = tags.themes.new_plant
    existing.theme_capacity_expansion = tags.themes.capacity_expansion
    existing.theme_land_acquisition = tags.themes.land_acquisition
    existing.theme_capex_approval = tags.themes.capex_approval
    existing.theme_fundraising = tags.themes.fundraising
    existing.capex_trigger = tags.themes.any_trigger


def _upsert_announcement(
    db: Session,
    item: dict,
    *,
    filing_type_override: str | None,
) -> tuple[bool, bool]:
    """Returns (inserted, updated)."""
    seq_id = str(item.get("seq_id") or "").strip()
    if not seq_id:
        return False, False

    nse_desc = item.get("desc") or ""
    body = item.get("attchmntText") or ""
    symbol = (item.get("symbol") or "").strip().upper()
    from invprom.ingest.nse_retag import refine_filing_type_for_row, tag_filing

    tags = tag_filing(attachment_text=body, subject=nse_desc, symbol=symbol)
    filing_type = refine_filing_type_for_row(nse_desc, tags, override=filing_type_override)

    existing = db.query(NseAnnouncement).filter(NseAnnouncement.seq_id == seq_id).one_or_none()
    inserted = existing is None
    if existing is None:
        existing = NseAnnouncement(seq_id=seq_id)
        db.add(existing)

    existing.symbol = symbol
    existing.company_name = (item.get("sm_name") or symbol or "Unknown")[:256]
    existing.subject = nse_desc[:256]
    existing.attachment_text = body
    existing.attachment_url = item.get("attchmntFile")
    existing.sort_date = _parse_sort_date(item.get("sort_date")) or _parse_sort_date(item.get("an_dt"))
    existing.raw_kind = "corporate-announcements"
    _apply_tags_to_row(existing, tags, filing_type)

    touch_listed_equity(db, symbol, existing.company_name)

    return inserted, not inserted


def sync_corporate_filings(
    db: Session,
    client: NseClient,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    chunk_days: int = 1,
) -> SyncResult:
    """
  Ingest high-value NSE corporate filing categories via subject= API filter
  (board outcomes, investor presentations, financial filings, earnings updates).
    """
    to_date = to_date or date.today()
    from_date = from_date or NseClient.default_sync_from_date(_get_sync_cursor(db, "corporate_filings"))

    subjects = NseClient.load_subject_feeds(settings.nse_subject_feeds_path)
    if not subjects:
        subjects = [{"subject": "Outcome of Board Meeting", "filing_type": "board_meeting_outcome"}]

    inserted = 0
    updated = 0
    fetched = 0

    for chunk_from, chunk_to in _date_chunks(from_date, to_date, chunk_days=chunk_days):
        for entry in subjects:
            subject = entry["subject"]
            type_override = entry.get("filing_type")
            rows = client.corporate_announcements(chunk_from, chunk_to, subject=subject)
            fetched += len(rows)
            for item in rows:
                ins, upd = _upsert_announcement(db, item, filing_type_override=type_override)
                if ins:
                    inserted += 1
                elif upd:
                    updated += 1
            db.commit()

    _set_sync_cursor(db, "corporate_filings", to_date)
    _refresh_company_announcement_counts(db)
    return SyncResult(
        "corporate_filings",
        from_date,
        to_date,
        fetched,
        inserted,
        updated,
        detail=f"{len(subjects)} NSE subject filters",
    )


def sync_announcements(
    db: Session,
    client: NseClient,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    chunk_days: int = 1,
) -> SyncResult:
    """Full corporate-announcements feed (large). Prefer sync_corporate_filings for daily use."""
    to_date = to_date or date.today()
    from_date = from_date or NseClient.default_sync_from_date(_get_sync_cursor(db, "all_announcements"))

    inserted = 0
    updated = 0
    fetched = 0

    for chunk_from, chunk_to in _date_chunks(from_date, to_date, chunk_days=chunk_days):
        rows = client.corporate_announcements(chunk_from, chunk_to)
        fetched += len(rows)
        for item in rows:
            ins, upd = _upsert_announcement(db, item, filing_type_override=None)
            if ins:
                inserted += 1
            elif upd:
                updated += 1
        db.commit()

    _set_sync_cursor(db, "all_announcements", to_date)
    _refresh_company_announcement_counts(db)
    return SyncResult("all_announcements", from_date, to_date, fetched, inserted, updated)


def sync_annual_reports(db: Session, client: NseClient) -> SyncResult:
    """Annual reports — per-symbol API for tickers in the local universe."""
    tickers = [c.ticker for c in db.query(Company).all()]
    inserted = 0
    updated = 0
    fetched = 0

    for ticker in tickers:
        rows = client.annual_reports(ticker)
        fetched += len(rows)
        for item in rows:
            file_name = (item.get("fileName") or "")[:512]
            from_yr = str(item.get("fromYr") or "")
            to_yr = str(item.get("toYr") or "")
            dedupe = f"{ticker}|{from_yr}|{to_yr}|{file_name[-120:]}"
            existing = db.query(NseAnnualReport).filter(NseAnnualReport.dedupe_key == dedupe).one_or_none()
            if existing is None:
                existing = NseAnnualReport(dedupe_key=dedupe)
                db.add(existing)
                inserted += 1
            else:
                updated += 1
            existing.symbol = ticker
            existing.company_name = (item.get("companyName") or ticker)[:256]
            existing.from_yr = from_yr[:16]
            existing.to_yr = to_yr[:16]
            existing.file_name = file_name
            if file_name.startswith("http"):
                existing.file_url = file_name
            elif file_name:
                existing.file_url = f"https://nsearchives.nseindia.com/{file_name.lstrip('/')}"
            else:
                existing.file_url = None
            existing.att_file_size = (item.get("attFileSize") or "")[:32]
            existing.broadcast_dttm = (item.get("broadcast_dttm") or "")[:64]
            db.commit()

    return SyncResult(
        "annual_reports",
        None,
        date.today(),
        fetched,
        inserted,
        updated,
        detail=f"{len(tickers)} symbols",
    )


def sync_corporate_actions(
    db: Session,
    client: NseClient,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> SyncResult:
    to_date = to_date or date.today()
    from_date = from_date or NseClient.default_sync_from_date(_get_sync_cursor(db, "corporate_actions"), fallback_days=30)

    inserted = 0
    updated = 0
    seen: set[str] = set()
    rows = client.corporate_actions(from_date, to_date)
    for item in rows:
        symbol = (item.get("symbol") or item.get("sym") or "").strip().upper()
        ex_date = (item.get("exDate") or item.get("exdate") or "")[:32]
        purpose = (item.get("subject") or item.get("purpose") or item.get("ind") or "")[:256]
        dedupe = f"{symbol}|{ex_date}|{purpose}"
        if dedupe in seen:
            continue
        seen.add(dedupe)
        existing = db.query(NseCorporateAction).filter(NseCorporateAction.dedupe_key == dedupe).one_or_none()
        if existing is None:
            existing = NseCorporateAction(dedupe_key=dedupe)
            db.add(existing)
            inserted += 1
        else:
            updated += 1
        existing.symbol = symbol
        existing.company_name = (item.get("comp") or item.get("company") or "")[:256]
        existing.ex_date = ex_date
        existing.purpose = purpose
        existing.record_date = (item.get("recDate") or item.get("recordDate") or "")[:32]
    db.commit()
    _set_sync_cursor(db, "corporate_actions", to_date)
    return SyncResult("corporate_actions", from_date, to_date, len(rows), inserted, updated)


def sync_events(
    db: Session,
    client: NseClient,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> SyncResult:
    """Upcoming board meetings / result dates (event calendar)."""
    to_date = to_date or date.today()
    from_date = from_date or NseClient.default_sync_from_date(_get_sync_cursor(db, "events"), fallback_days=14)

    inserted = 0
    updated = 0
    seen: set[str] = set()
    rows = client.event_calendar(from_date, to_date)
    for item in rows:
        symbol = (item.get("symbol") or "").strip().upper()
        event_date = (item.get("date") or "")[:32]
        purpose = (item.get("purpose") or item.get("bm_desc") or "")[:512]
        dedupe = f"{symbol}|{event_date}|{purpose[:200]}"
        if dedupe in seen:
            continue
        seen.add(dedupe)
        existing = db.query(NseEvent).filter(NseEvent.dedupe_key == dedupe).one_or_none()
        if existing is None:
            existing = NseEvent(dedupe_key=dedupe)
            db.add(existing)
            inserted += 1
        else:
            updated += 1
        existing.symbol = symbol
        existing.company_name = (item.get("company") or "")[:256]
        existing.event_date = event_date
        existing.purpose = purpose
        existing.filing_type = "upcoming_board_meeting"
    db.commit()
    _set_sync_cursor(db, "events", to_date)
    return SyncResult("events", from_date, to_date, len(rows), inserted, updated)


def sync_all_feeds(
    db: Session,
    *,
    days: int = 3,
    include_actions: bool = False,
    include_events: bool = True,
    include_annual_reports: bool = True,
    full_announcements: bool = False,
    sync_universe: bool = True,
    chunk_days: int = 1,
) -> list[SyncResult]:
    to_date = date.today()
    from_date = to_date - timedelta(days=days)
    results: list[SyncResult] = []
    with NseClient() as client:
        if sync_universe:
            stats = sync_listed_equities(db, client)
            results.append(
                SyncResult(
                    "nse_listed_universe",
                    None,
                    to_date,
                    stats["equity_symbols"],
                    stats["inserted"],
                    stats["updated"],
                    detail="All NSE EQ symbols",
                )
            )
            idx_stats = sync_nse_index_classifiers(db)
            results.append(
                SyncResult(
                    "nse_index_classifiers",
                    None,
                    to_date,
                    idx_stats["classifier_rows"],
                    idx_stats["classifier_rows"],
                    0,
                    detail="NSE index CSV membership",
                )
            )
        if full_announcements:
            results.append(
                sync_announcements(db, client, from_date=from_date, to_date=to_date, chunk_days=chunk_days)
            )
        else:
            results.append(
                sync_corporate_filings(db, client, from_date=from_date, to_date=to_date, chunk_days=chunk_days)
            )
        if include_events:
            results.append(sync_events(db, client, from_date=from_date, to_date=to_date))
        if include_actions:
            results.append(sync_corporate_actions(db, client, from_date=from_date, to_date=to_date))
        if include_annual_reports:
            results.append(sync_annual_reports(db, client))
        refresh_listed_equity_names(db)
    return results


def backfill_market_filings(db: Session, *, days: int = 30, chunk_days: int = 3) -> list[SyncResult]:
    """Pull NSE corporate filings for all listed companies over a historical window (default 1 month)."""
    return sync_all_feeds(
        db,
        days=days,
        include_events=False,
        include_actions=False,
        include_annual_reports=False,
        sync_universe=True,
        chunk_days=chunk_days,
    )


def _refresh_company_announcement_counts(db: Session) -> None:
    cutoff = datetime.utcnow() - timedelta(days=365)
    companies = {c.ticker: c for c in db.query(Company).all()}
    if not companies:
        return

    rows = (
        db.query(
            NseAnnouncement.symbol,
            func.count().filter(NseAnnouncement.capex_trigger.is_(True)),
            func.count().filter(NseAnnouncement.mentions_odisha.is_(True)),
            func.count().filter(NseAnnouncement.is_management_guidance.is_(True)),
        )
        .filter(NseAnnouncement.sort_date.is_not(None), NseAnnouncement.sort_date >= cutoff)
        .group_by(NseAnnouncement.symbol)
        .all()
    )

    for symbol, expansion_ct, odisha_ct, guidance_ct in rows:
        company = companies.get(symbol)
        if company is None:
            continue
        period = (
            db.query(FinancialPeriod)
            .filter(FinancialPeriod.company_id == company.id)
            .order_by(FinancialPeriod.fy.desc())
            .first()
        )
        if period is None:
            continue
        period.expansion_announcements_12m = int(expansion_ct or 0)
        period.odisha_news_hits_12m = int(odisha_ct or 0)
        period.management_guidance_hits_12m = int(guidance_ct or 0)
    db.commit()
