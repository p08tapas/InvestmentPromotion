from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from invprom.db.models import NseAnnouncement, NseListedEquity
from invprom.ingest.nse_client import NseClient


def touch_listed_equity(db: Session, symbol: str, company_name: str | None) -> None:
    """Update company name on the symbol master; create row only if missing."""
    if not symbol:
        return
    equity = db.query(NseListedEquity).filter(NseListedEquity.symbol == symbol).one_or_none()
    if equity is not None:
        if company_name:
            equity.company_name = company_name[:256]
            equity.updated_at = datetime.utcnow()
        return
    try:
        with db.begin_nested():
            db.add(NseListedEquity(symbol=symbol, series="EQ", company_name=(company_name or None)))
    except IntegrityError:
        pass
    equity = db.query(NseListedEquity).filter(NseListedEquity.symbol == symbol).one_or_none()
    if equity and company_name:
        equity.company_name = company_name[:256]
        equity.updated_at = datetime.utcnow()


def sync_listed_equities(db: Session, client: NseClient) -> dict[str, int]:
    """Load all NSE EQ symbols from the public pre-open market API (~2.3k instruments)."""
    payload = client.get_json("/api/market-data-pre-open", {"key": "ALL"})
    rows = payload.get("data") if isinstance(payload, dict) else []
    inserted = 0
    updated = 0
    seen = 0

    for item in rows or []:
        meta = item.get("metadata") if isinstance(item, dict) else None
        if not meta:
            continue
        symbol = (meta.get("symbol") or "").strip().upper()
        series = (meta.get("series") or "EQ").strip().upper()
        if not symbol or series != "EQ":
            continue
        seen += 1
        existing = db.query(NseListedEquity).filter(NseListedEquity.symbol == symbol).one_or_none()
        if existing is None:
            db.add(NseListedEquity(symbol=symbol, series=series))
            inserted += 1
        else:
            existing.series = series
            updated += 1

    db.commit()
    refresh_listed_equity_names(db)
    return {"equity_symbols": seen, "inserted": inserted, "updated": updated}


def refresh_listed_equity_names(db: Session) -> int:
    count = 0
    for eq in db.query(NseListedEquity).all():
        ann = (
            db.query(NseAnnouncement)
            .filter(NseAnnouncement.symbol == eq.symbol)
            .order_by(NseAnnouncement.sort_date.desc())
            .first()
        )
        if ann and ann.company_name and ann.company_name != eq.company_name:
            eq.company_name = ann.company_name[:256]
            count += 1
    db.commit()
    return count


def universe_stats(db: Session) -> dict[str, int]:
    total = db.query(NseListedEquity).count()
    with_names = db.query(NseListedEquity).filter(NseListedEquity.company_name.is_not(None)).count()
    return {"listed_equities": total, "listed_with_company_name": with_names}
