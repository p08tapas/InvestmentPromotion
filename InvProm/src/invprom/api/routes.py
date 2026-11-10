from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from invprom.api.schemas import (
    CompanyScoreOut,
    DossierOut,
    NseAnnualReportOut,
    NseAnnouncementOut,
    NseSyncResultOut,
)
from invprom.config import settings
from invprom.db.models import (
    Company,
    FinancialPeriod,
    NseAnnouncement,
    NseAnnualReport,
    NseSymbolClassifier,
    NseSyncState,
    ScoreSnapshot,
)
from invprom.db.session import get_db
from invprom.ingest.csv_financials import load_financials_csv
from invprom.ingest.nse_index_csv import classifier_catalog
from invprom.ingest.nse_sync import SyncResult, backfill_market_filings, sync_all_feeds
from invprom.ingest.nse_universe import universe_stats
from invprom.services.capex_metrics import capex_metrics
from invprom.services.pdf_enrich import enrich_announcement_pdfs
from invprom.services.rescore import rescore_all

router = APIRouter()


def _company_score_out(company: Company, period: FinancialPeriod | None, score: ScoreSnapshot) -> CompanyScoreOut:
    return CompanyScoreOut(
        ticker=company.ticker,
        name=company.name,
        sector_id=company.sector_id,
        fy=period.fy if period else None,
        tier=score.tier,
        ipicol_priority=score.ipicol_priority,
        sector_fit=score.sector_fit,
        odisha_affinity=score.odisha_affinity,
        signal_cash_reserves=score.signal_cash_reserves,
        signal_management_guidance=score.signal_management_guidance,
        signal_capacity_utilization=score.signal_capacity_utilization,
        signal_order_book=score.signal_order_book,
        signal_government_incentives=score.signal_government_incentives,
        expansion_momentum=score.expansion_momentum,
        capital_availability=score.capital_availability,
        computed_at=score.computed_at,
    )


def _latest_scores(db: Session) -> list[tuple[Company, FinancialPeriod | None, ScoreSnapshot]]:
    out: list[tuple[Company, FinancialPeriod | None, ScoreSnapshot]] = []
    companies = db.query(Company).all()
    for company in companies:
        score = (
            db.query(ScoreSnapshot)
            .filter(ScoreSnapshot.company_id == company.id)
            .order_by(ScoreSnapshot.computed_at.desc())
            .first()
        )
        if score is None:
            continue
        period = (
            db.query(FinancialPeriod)
            .filter(FinancialPeriod.company_id == company.id)
            .order_by(FinancialPeriod.fy.desc())
            .first()
        )
        out.append((company, period, score))
    return out


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": "invprom", "model": settings.score_model_version}


@router.post("/admin/init-db")
def admin_init_db() -> dict[str, str]:
    from invprom.db.session import init_db

    init_db()
    return {"status": "initialized"}


@router.post("/ingest/csv")
async def ingest_csv(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict[str, int | str]:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a .csv file")
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.data_dir / "uploads" / file.filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    dest.write_bytes(content)
    rows = load_financials_csv(db, dest)
    return {"rows_loaded": rows, "path": str(dest)}


@router.post("/scores/recompute")
def recompute_scores(db: Session = Depends(get_db)) -> dict[str, int]:
    n = rescore_all(db)
    return {"scored": n}


@router.get("/pipeline", response_model=list[CompanyScoreOut])
def pipeline(
    db: Session = Depends(get_db),
    tier: str | None = Query(None, pattern="^[ABC]$"),
    sector_id: str | None = None,
    min_priority: float | None = None,
    limit: int = Query(200, ge=1, le=1000),
) -> list[CompanyScoreOut]:
    from invprom.services.nse_pipeline import ensure_pipeline_companies_from_nse

    ensure_pipeline_companies_from_nse(db)
    rows = _latest_scores(db)
    result: list[CompanyScoreOut] = []
    for company, period, score in rows:
        if tier and score.tier != tier:
            continue
        if sector_id and company.sector_id != sector_id:
            continue
        if min_priority is not None and score.ipicol_priority < min_priority:
            continue
        result.append(_company_score_out(company, period, score))
    result.sort(key=lambda x: x.ipicol_priority, reverse=True)
    return result[:limit]


@router.get("/companies/{ticker}", response_model=DossierOut)
def company_dossier(ticker: str, db: Session = Depends(get_db)) -> DossierOut:
    company = db.query(Company).filter(Company.ticker == ticker.upper()).one_or_none()
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    score = (
        db.query(ScoreSnapshot)
        .filter(ScoreSnapshot.company_id == company.id)
        .order_by(ScoreSnapshot.computed_at.desc())
        .first()
    )
    if score is None:
        raise HTTPException(status_code=404, detail="No score yet; run recompute")
    period = (
        db.query(FinancialPeriod)
        .filter(FinancialPeriod.company_id == company.id)
        .order_by(FinancialPeriod.fy.desc())
        .first()
    )
    try:
        breakdown = json.loads(score.breakdown_json)
    except json.JSONDecodeError:
        breakdown = {}

    return DossierOut(company=_company_score_out(company, period, score), breakdown=breakdown)


@router.get("/framework/signals")
def banker_signal_framework() -> dict[str, object]:
    """How investment bankers track capex deployment — encoded in scoring v2."""
    return {
        "model_version": settings.score_model_version,
        "doc": "docs/SIGNALS.md",
        "summary": (
            "Each company receives a composite priority score (0–100) from five banker-style capex signals "
            "(cash, guidance, capacity, order book, incentives) plus sector fit vs West Bengal’s focus industries. "
            "NSE filings refresh guidance/expansion counts; detailed balance-sheet fields can be imported via CSV. "
            "Tier A/B/C ranks who to engage before they commit capital elsewhere."
        ),
        "signals": [
            {
                "id": 1,
                "name": "Large cash reserves",
                "metrics": ["net_cash_cr", "net_cash_to_market_cap"],
                "csv_fields": ["cash_cr", "investments_cr", "total_debt_cr", "market_cap_cr"],
            },
            {
                "id": 2,
                "name": "Management guidance",
                "sources": ["NSE/BSE announcements", "investor presentations", "earnings calls"],
                "csv_fields": ["management_guidance_hits_12m"],
                "nse_field": "is_management_guidance",
            },
            {
                "id": 3,
                "name": "Capacity utilization",
                "heuristic": "90-95% → expansion likely; ~60% → low urgency",
                "csv_fields": ["capacity_utilization_pct"],
            },
            {
                "id": 4,
                "name": "Order book growth",
                "sectors": ["defense_infra", "capital_goods"],
                "csv_fields": ["order_book_cr", "order_book_prev_yr_cr"],
            },
            {
                "id": 5,
                "name": "Government incentives",
                "sources": ["PLI and allied schemes"],
                "csv_fields": ["pli_beneficiary"],
                "config": "data/government_incentives.json",
            },
        ],
        "methodology": {
            "formula": (
                "Composite score = 0.14×Cash + 0.14×Guidance + 0.14×Capacity + 0.14×Order book "
                "+ 0.14×Incentives + 0.30×Sector fit (each sub-score is 0–100)."
            ),
            "weights": {
                "signal_cash_reserves": 0.14,
                "signal_management_guidance": 0.14,
                "signal_capacity_utilization": 0.14,
                "signal_order_book": 0.14,
                "signal_government_incentives": 0.14,
                "sector_fit": 0.30,
            },
            "data_sources": [
                "NSE corporate filings (auto) — expansion/guidance hit counts, capex theme flags",
                "Optional CSV import — balance sheet, capacity %, order book, PLI flag",
                "data/sector_taxonomy.json — sector keywords for fit score",
            ],
            "tier_rules": [
                "Tier A: composite ≥ 70 and (cash ≥ 55 or guidance ≥ 55)",
                "Tier B: composite ≥ 52",
                "Tier C: all others",
            ],
            "pipeline_columns": {
                "Score": "Composite priority (sort key, higher = engage sooner)",
                "Cash": "Signal 1 — net cash / market cap vs deployment heuristics",
                "Guidance": "Signal 2 — management guidance + capex announcement frequency (NSE)",
                "Capacity": "Signal 3 — utilisation % where applicable to sector",
                "Orders": "Signal 4 — order-book growth YoY (EPC/capital goods)",
                "PLI": "Signal 5 — PLI / policy-linked incentive exposure",
            },
            "nse_windows": (
                "Use Sync NSE (3 days) for a short operational window; Backfill (30 days) for a monthly view. "
                "NSE Status, Capex triggers, and Filings tabs follow the active window."
            ),
        },
    }


def _sync_result_out(r: SyncResult) -> NseSyncResultOut:
    return NseSyncResultOut(
        feed=r.feed,
        from_date=r.from_date.isoformat() if r.from_date else None,
        to_date=r.to_date.isoformat() if r.to_date else None,
        fetched=r.fetched,
        inserted=r.inserted,
        updated=r.updated,
        detail=r.detail,
    )


CAPEX_THEME_FIELDS = {
    "new_plant": NseAnnouncement.theme_new_plant,
    "capacity_expansion": NseAnnouncement.theme_capacity_expansion,
    "land_acquisition": NseAnnouncement.theme_land_acquisition,
    "capex_approval": NseAnnouncement.theme_capex_approval,
    "fundraising": NseAnnouncement.theme_fundraising,
}


def _query_filings(db: Session, **filters: object) -> Any:
    q = db.query(NseAnnouncement).order_by(NseAnnouncement.sort_date.desc())
    symbol = filters.get("symbol")
    if symbol:
        q = q.filter(NseAnnouncement.symbol == str(symbol).upper())
    if filters.get("filing_type"):
        q = q.filter(NseAnnouncement.filing_type == filters["filing_type"])
    if filters.get("ipicol_relevant") is True:
        q = q.filter(NseAnnouncement.is_ipicol_relevant.is_(True))
    if filters.get("capex_trigger"):
        q = q.filter(NseAnnouncement.capex_trigger.is_(True))
    if filters.get("financial_results"):
        q = q.filter(NseAnnouncement.is_financial_results.is_(True))
    theme = filters.get("theme")
    if theme and theme in CAPEX_THEME_FIELDS:
        q = q.filter(CAPEX_THEME_FIELDS[str(theme)].is_(True))
    if filters.get("odisha_only"):
        q = q.filter(NseAnnouncement.mentions_odisha.is_(True))
    since_days = filters.get("since_days")
    if since_days:
        cutoff = datetime.utcnow() - timedelta(days=int(since_days))
        q = q.filter(NseAnnouncement.sort_date.is_not(None), NseAnnouncement.sort_date >= cutoff)
    classifier_id = filters.get("classifier_id")
    if classifier_id:
        symbols_q = (
            db.query(NseSymbolClassifier.symbol)
            .filter(NseSymbolClassifier.classifier_id == str(classifier_id))
            .distinct()
        )
        q = q.filter(NseAnnouncement.symbol.in_(symbols_q))
    return q


def _filings_count(db: Session, *, since_days: int | None = None, classifier_id: str | None = None, **filters: object) -> int:
    q = _query_filings(db, since_days=since_days, classifier_id=classifier_id, **filters)
    return q.count()


def _iso_or_none(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


@router.post("/nse/sync", response_model=list[NseSyncResultOut])
def nse_sync(
    db: Session = Depends(get_db),
    days: int = Query(3, ge=1, le=30),
    full_announcements: bool = Query(
        False,
        description="If true, downloads the full announcements feed (heavy). Default: subject-filtered filings only.",
    ),
    annual_reports: bool = Query(True),
    recompute_scores: bool = Query(True),
) -> list[NseSyncResultOut]:
    """Sync NSE corporate filings (board outcomes, presentations, results) + optional annual reports."""
    try:
        results = sync_all_feeds(
            db,
            days=days,
            full_announcements=full_announcements,
            include_annual_reports=annual_reports,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"NSE sync failed: {exc}") from exc
    if recompute_scores:
        rescore_all(db)
    return [_sync_result_out(r) for r in results]


@router.post("/nse/backfill", response_model=list[NseSyncResultOut])
def nse_backfill(
    db: Session = Depends(get_db),
    days: int = Query(30, ge=7, le=120, description="Historical window (default 1 month)"),
    chunk_days: int = Query(3, ge=1, le=7),
) -> list[NseSyncResultOut]:
    """Backfill NSE filings for all listed EQ companies (market-wide, all configured subjects)."""
    try:
        results = backfill_market_filings(db, days=days, chunk_days=chunk_days)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"NSE backfill failed: {exc}") from exc
    return [_sync_result_out(r) for r in results]


@router.get("/nse/classifiers")
def nse_classifiers(
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=365, description="Count filings in the last N days per NSE index"),
) -> list[dict[str, object]]:
    """NSE index constituent classifiers (Midcap 100, Pharma, Infrastructure, …) from official index CSVs."""
    catalog = classifier_catalog()
    sym_rows = db.query(NseSymbolClassifier.classifier_id, NseSymbolClassifier.symbol).all()
    symbols_by_classifier: dict[str, set[str]] = {}
    for cid, sym in sym_rows:
        symbols_by_classifier.setdefault(str(cid), set()).add(str(sym))

    cutoff = datetime.utcnow() - timedelta(days=days)
    out: list[dict[str, object]] = []
    for item in catalog:
        cid = item["id"]
        sym_set = symbols_by_classifier.get(cid, set())
        filing_count = 0
        if sym_set:
            filing_count = (
                db.query(NseAnnouncement)
                .filter(
                    NseAnnouncement.symbol.in_(sym_set),
                    NseAnnouncement.sort_date.is_not(None),
                    NseAnnouncement.sort_date >= cutoff,
                )
                .count()
            )
        out.append(
            {
                **item,
                "constituent_count": len(sym_set),
                f"filings_last_{days}_days": filing_count,
            }
        )
    return out


@router.get("/nse/history", response_model=list[NseAnnouncementOut])
def nse_history(
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=365),
    symbol: str | None = None,
    filing_type: str | None = None,
    classifier: str | None = Query(None, alias="classifier", description="NSE index classifier id e.g. midcap_100, pharma"),
    classifier_id: str | None = Query(None, description="Alias for classifier"),
    capex_trigger: bool = False,
    limit: int = Query(500, ge=1, le=500),
) -> list[NseAnnouncementOut]:
    """Filings in the last N days (default 30) across the full NSE equity market."""
    cid = classifier_id or classifier
    return _list_filings(
        db,
        symbol=symbol,
        filing_type=filing_type,
        classifier_id=cid,
        capex_trigger=True if capex_trigger else None,
        since_days=days,
        limit=limit,
    )


@router.get("/nse/history/grouped")
def nse_history_grouped(
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=365),
    filing_type: str | None = None,
    capex_trigger: bool = False,
    limit_per_classifier: int = Query(80, ge=1, le=200),
) -> dict[str, object]:
    """Last-month filings segregated by NSE index classifier (constituent lists from NSE)."""
    from sqlalchemy import func as sa_func

    cutoff = datetime.utcnow() - timedelta(days=days)
    stored_min, stored_max = (
        db.query(sa_func.min(NseAnnouncement.sort_date), sa_func.max(NseAnnouncement.sort_date))
        .filter(NseAnnouncement.sort_date.is_not(None))
        .one()
    )
    groups: list[dict[str, object]] = []
    for item in classifier_catalog():
        cid = item["id"]
        total = _filings_count(
            db,
            since_days=days,
            classifier_id=cid,
            filing_type=filing_type,
            capex_trigger=True if capex_trigger else None,
        )
        rows = _list_filings(
            db,
            classifier_id=cid,
            filing_type=filing_type,
            capex_trigger=True if capex_trigger else None,
            since_days=days,
            limit=limit_per_classifier,
        )
        groups.append(
            {
                "classifier_id": cid,
                "label": item.get("label", cid),
                "total_filings": total,
                "showing": len(rows),
                "filings": [NseAnnouncementOut.model_validate(r) for r in rows],
            }
        )
    window_min, window_max = (
        db.query(sa_func.min(NseAnnouncement.sort_date), sa_func.max(NseAnnouncement.sort_date))
        .filter(NseAnnouncement.sort_date.is_not(None), NseAnnouncement.sort_date >= cutoff)
        .one()
    )
    return {
        "days": days,
        "stored_date_range": {"min": _iso_or_none(stored_min), "max": _iso_or_none(stored_max)},
        "window_date_range": {"min": _iso_or_none(window_min), "max": _iso_or_none(window_max)},
        "classifier_groups": groups,
    }


@router.get("/nse/status")
def nse_status(
    db: Session = Depends(get_db),
    days: int = Query(30, ge=1, le=365, description="Window for capex + filing counts on this page"),
) -> dict[str, object]:
    from sqlalchemy import func as sa_func

    feeds = db.query(NseSyncState).all()
    capex = capex_metrics(db, since_days=days)
    rows = db.query(NseAnnouncement.filing_type, sa_func.count()).group_by(NseAnnouncement.filing_type).all()
    by_filing_type = {str(k): int(v) for k, v in rows}
    cutoff = datetime.utcnow() - timedelta(days=days)
    filings_in_window = (
        db.query(NseAnnouncement)
        .filter(NseAnnouncement.sort_date.is_not(None), NseAnnouncement.sort_date >= cutoff)
        .count()
    )
    symbols_in_window = (
        db.query(NseAnnouncement.symbol)
        .filter(NseAnnouncement.sort_date.is_not(None), NseAnnouncement.sort_date >= cutoff)
        .distinct()
        .count()
    )
    stored_min, stored_max = (
        db.query(sa_func.min(NseAnnouncement.sort_date), sa_func.max(NseAnnouncement.sort_date))
        .filter(NseAnnouncement.sort_date.is_not(None))
        .one()
    )
    window_min, window_max = stored_min, stored_max
    if filings_in_window:
        window_min, window_max = (
            db.query(sa_func.min(NseAnnouncement.sort_date), sa_func.max(NseAnnouncement.sort_date))
            .filter(NseAnnouncement.sort_date.is_not(None), NseAnnouncement.sort_date >= cutoff)
            .one()
        )
    classifier_rows = db.query(NseSymbolClassifier).count()

    return {
        "source_page": "https://www.nseindia.com/companies-listing/corporate-filings-actions",
        "doc": "docs/NSE_FILINGS.md",
        "announcements_stored": db.query(NseAnnouncement).count(),
        "annual_reports_stored": db.query(NseAnnualReport).count(),
        "by_filing_type": by_filing_type,
        "feeds": {row.feed: row.last_to_date.isoformat() for row in feeds},
        "capex_all_ui_path": "/ui?tab=capex",
        "status_window_days": days,
        "history_30d_ui_path": "/ui?tab=history",
        "filings_last_30_days": filings_in_window,
        "symbols_with_filings_30d": symbols_in_window,
        "filings_in_window_days": filings_in_window,
        "symbols_with_filings_in_window": symbols_in_window,
        "filings_stored_date_range": {"min": _iso_or_none(stored_min), "max": _iso_or_none(stored_max)},
        "filings_last_30d_date_range": {"min": _iso_or_none(window_min), "max": _iso_or_none(window_max)},
        "filings_window_date_range": {"min": _iso_or_none(window_min), "max": _iso_or_none(window_max)},
        "nse_index_classifiers_loaded": classifier_rows,
        "pdf_extract_api": "POST /api/nse/extract-pdfs",
        **universe_stats(db),
        **capex,
    }


def _list_filings(
    db: Session,
    *,
    symbol: str | None = None,
    filing_type: str | None = None,
    theme: str | None = None,
    classifier_id: str | None = None,
    capex_trigger: bool | None = None,
    financial_results: bool | None = None,
    odisha_only: bool | None = None,
    since_days: int | None = None,
    limit: int = 50,
) -> list[NseAnnouncement]:
    q = _query_filings(
        db,
        symbol=symbol,
        filing_type=filing_type,
        theme=theme,
        classifier_id=classifier_id,
        capex_trigger=capex_trigger,
        financial_results=financial_results,
        odisha_only=odisha_only,
        since_days=since_days,
    )
    return q.limit(limit).all()


@router.get("/nse/filings", response_model=list[NseAnnouncementOut])
def nse_filings(
    db: Session = Depends(get_db),
    symbol: str | None = None,
    filing_type: str | None = Query(
        None,
        description="board_meeting_outcome | investor_presentation | financial_results | earnings_call_update | ...",
    ),
    theme: str | None = Query(None, description="new_plant | capacity_expansion | land_acquisition | capex_approval | fundraising"),
    capex_trigger: bool = False,
    financial_results: bool = False,
    odisha_only: bool = False,
    days: int | None = Query(None, ge=1, le=365, description="Limit to filings with sort_date in the last N days"),
    limit: int = Query(50, ge=1, le=500),
) -> list[NseAnnouncementOut]:
    return _list_filings(
        db,
        symbol=symbol,
        filing_type=filing_type,
        theme=theme,
        capex_trigger=True if capex_trigger else None,
        financial_results=True if financial_results else None,
        odisha_only=True if odisha_only else None,
        since_days=days,
        limit=limit,
    )


@router.get("/nse/filings/{seq_id}", response_model=NseAnnouncementOut)
def nse_filing_detail(seq_id: str, db: Session = Depends(get_db)) -> NseAnnouncement:
    row = db.query(NseAnnouncement).filter(NseAnnouncement.seq_id == seq_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Filing not found")
    return row


@router.post("/nse/retag")
def nse_retag(db: Session = Depends(get_db)) -> dict[str, int]:
    """Re-apply filing/capex tags on all stored announcements (e.g. after rule fixes)."""
    from invprom.ingest.nse_retag import retag_all_announcements

    return retag_all_announcements(db)


@router.post("/nse/extract-pdfs")
def nse_extract_pdfs(
    db: Session = Depends(get_db),
    limit: int = Query(15, ge=1, le=50),
    recompute_scores: bool = Query(False),
) -> dict[str, object]:
    """Download PDF attachments and extract text for deeper capex keyword detection."""
    result = enrich_announcement_pdfs(db, limit=limit)
    if recompute_scores:
        result["rescored"] = rescore_all(db)
    return result


@router.get("/nse/capex-triggers", response_model=list[NseAnnouncementOut])
def nse_capex_triggers(
    db: Session = Depends(get_db),
    theme: str | None = None,
    symbol: str | None = None,
    days: int | None = Query(None, ge=1, le=365, description="Limit to filings with sort_date in the last N days"),
    limit: int = Query(100, ge=1, le=500),
) -> list[NseAnnouncementOut]:
    return _list_filings(
        db,
        symbol=symbol,
        theme=theme,
        capex_trigger=True,
        since_days=days,
        limit=limit,
    )


@router.get("/nse/annual-reports", response_model=list[NseAnnualReportOut])
def nse_annual_reports_list(db: Session = Depends(get_db), symbol: str | None = None) -> list[NseAnnualReportOut]:
    q = db.query(NseAnnualReport).order_by(NseAnnualReport.to_yr.desc())
    if symbol:
        q = q.filter(NseAnnualReport.symbol == symbol.upper())
    return q.all()


@router.get("/nse/announcements", response_model=list[NseAnnouncementOut], deprecated=True)
def nse_announcements(
    db: Session = Depends(get_db),
    symbol: str | None = None,
    ipicol_relevant: bool | None = None,
    expansion_only: bool | None = None,
    guidance_only: bool | None = None,
    odisha_only: bool | None = None,
    limit: int = Query(50, ge=1, le=500),
) -> list[NseAnnouncementOut]:
    q = db.query(NseAnnouncement).order_by(NseAnnouncement.sort_date.desc())
    if symbol:
        q = q.filter(NseAnnouncement.symbol == symbol.upper())
    if ipicol_relevant is True:
        q = q.filter(NseAnnouncement.is_ipicol_relevant.is_(True))
    if expansion_only:
        q = q.filter(NseAnnouncement.capex_trigger.is_(True))
    if guidance_only:
        q = q.filter(NseAnnouncement.is_management_guidance.is_(True))
    if odisha_only:
        q = q.filter(NseAnnouncement.mentions_odisha.is_(True))
    return q.limit(limit).all()


@router.post("/bootstrap/sample-data")
def bootstrap_sample_data(db: Session = Depends(get_db)) -> dict[str, int]:
    sample = Path(settings.data_dir) / "sample_financials.csv"
    if not sample.is_file():
        raise HTTPException(status_code=404, detail=f"Missing {sample}")
    rows = load_financials_csv(db, sample)
    scored = rescore_all(db)
    return {"rows_loaded": rows, "scored": scored}
