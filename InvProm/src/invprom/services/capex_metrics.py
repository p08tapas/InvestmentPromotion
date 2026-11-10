from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import Integer, func
from sqlalchemy.orm import Session

from invprom.db.models import NseAnnouncement

THEME_FIELDS: tuple[tuple[str, str], ...] = (
    ("new_plant", "theme_new_plant"),
    ("capacity_expansion", "theme_capacity_expansion"),
    ("land_acquisition", "theme_land_acquisition"),
    ("capex_approval", "theme_capex_approval"),
    ("fundraising", "theme_fundraising"),
)

THEME_LABELS = {
    "new_plant": "New plant",
    "capacity_expansion": "Capacity expansion",
    "land_acquisition": "Land acquisition",
    "capex_approval": "Capex approval",
    "fundraising": "Fundraising",
}


def reconcile_capex_trigger_flags(db: Session) -> int:
    """Ensure capex_trigger matches OR of the five theme booleans (fixes legacy rows)."""
    fixed = 0
    for row in db.query(NseAnnouncement).yield_per(500):
        any_theme = any(getattr(row, attr) for _, attr in THEME_FIELDS)
        if row.capex_trigger != any_theme:
            row.capex_trigger = any_theme
            fixed += 1
    if fixed:
        db.commit()
    return fixed


def _announcement_window_q(db: Session, since_days: int | None):
    q = db.query(NseAnnouncement)
    if since_days is not None:
        cutoff = datetime.utcnow() - timedelta(days=int(since_days))
        q = q.filter(NseAnnouncement.sort_date.is_not(None), NseAnnouncement.sort_date >= cutoff)
    return q


def capex_theme_counts(db: Session, *, since_days: int | None = None) -> dict[str, int]:
    out: dict[str, int] = {}
    for key, col in THEME_FIELDS:
        q = _announcement_window_q(db, since_days).filter(getattr(NseAnnouncement, col).is_(True))
        out[key] = q.count()
    return out


def capex_metrics(db: Session, *, since_days: int | None = None) -> dict[str, object]:
    reconcile_capex_trigger_flags(db)
    by_theme = capex_theme_counts(db, since_days=since_days)
    theme_tag_total = sum(by_theme.values())
    unique_filings = (
        _announcement_window_q(db, since_days).filter(NseAnnouncement.capex_trigger.is_(True)).count()
    )

    multi_theme_filings = (
        _announcement_window_q(db, since_days)
        .filter(NseAnnouncement.capex_trigger.is_(True))
        .filter(
            (
                func.cast(NseAnnouncement.theme_new_plant, Integer)
                + func.cast(NseAnnouncement.theme_capacity_expansion, Integer)
                + func.cast(NseAnnouncement.theme_land_acquisition, Integer)
                + func.cast(NseAnnouncement.theme_capex_approval, Integer)
                + func.cast(NseAnnouncement.theme_fundraising, Integer)
            )
            > 1
        )
        .count()
    )

    themes_with_links = [
        {
            "id": key,
            "label": THEME_LABELS[key],
            "count": count,
            "filter_url": f"/api/nse/capex-triggers?theme={key}&limit=200",
            "ui_path": f"/ui?tab=capex&theme={key}",
        }
        for key, count in by_theme.items()
    ]

    window_note = (
        f" Counts cover the last {since_days} day(s) of filing dates in SQLite."
        if since_days is not None
        else " Counts cover all stored filings."
    )

    return {
        "capex_window_days": since_days,
        "capex_filing_count": unique_filings,
        "capex_theme_tag_total": theme_tag_total,
        "capex_triggers": unique_filings,
        "by_capex_theme": by_theme,
        "themes": themes_with_links,
        "filings_with_multiple_themes": multi_theme_filings,
        "metrics_note": (
            "capex_filing_count is unique NSE filings with at least one capex theme. "
            "capex_theme_tag_total sums per-theme flags; one filing can contribute to multiple themes."
            + window_note
        ),
    }
