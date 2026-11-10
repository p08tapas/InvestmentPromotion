from __future__ import annotations

import csv
from pathlib import Path

from sqlalchemy.orm import Session

from invprom.db.models import Company, FinancialPeriod


def _parse_bool(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y"}


def _parse_float(value: str | None) -> float | None:
    if value is None or value.strip() == "":
        return None
    return float(value)


def _parse_int(value: str | None) -> int:
    if value is None or value.strip() == "":
        return 0
    return int(float(value))


def load_financials_csv(db: Session, path: Path) -> int:
    """Load companies and banker-signal inputs from CSV (annual report / manual research)."""
    rows_loaded = 0
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = (row.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            name = (row.get("company_name") or ticker).strip()
            sector_id = (row.get("sector_id") or "").strip() or None
            fy = int(float(row.get("fy") or 0))
            if fy <= 0:
                continue

            company = db.query(Company).filter(Company.ticker == ticker).one_or_none()
            if company is None:
                company = Company(ticker=ticker, name=name, sector_id=sector_id)
                db.add(company)
                db.flush()
            else:
                company.name = name
                company.sector_id = sector_id

            period = (
                db.query(FinancialPeriod)
                .filter(FinancialPeriod.company_id == company.id, FinancialPeriod.fy == fy)
                .one_or_none()
            )
            if period is None:
                period = FinancialPeriod(company_id=company.id, fy=fy)
                db.add(period)

            period.revenue_cr = _parse_float(row.get("revenue_cr"))
            period.capex_cr = _parse_float(row.get("capex_cr"))
            period.cash_cr = _parse_float(row.get("cash_cr"))
            period.total_debt_cr = _parse_float(row.get("total_debt_cr"))
            period.investments_cr = _parse_float(row.get("investments_cr"))
            period.market_cap_cr = _parse_float(row.get("market_cap_cr"))
            period.capex_prev_yr_cr = _parse_float(row.get("capex_prev_yr_cr"))
            period.revenue_prev_yr_cr = _parse_float(row.get("revenue_prev_yr_cr"))
            period.capacity_utilization_pct = _parse_float(row.get("capacity_utilization_pct"))
            period.order_book_cr = _parse_float(row.get("order_book_cr"))
            period.order_book_prev_yr_cr = _parse_float(row.get("order_book_prev_yr_cr"))
            period.pli_beneficiary = _parse_bool(row.get("pli_beneficiary"))
            period.odisha_presence = _parse_bool(row.get("odisha_presence"))
            period.odisha_news_hits_12m = _parse_int(row.get("odisha_news_hits_12m"))
            period.expansion_announcements_12m = _parse_int(row.get("expansion_announcements_12m"))
            period.management_guidance_hits_12m = _parse_int(row.get("management_guidance_hits_12m"))
            period.source_note = (row.get("source_note") or "csv_import").strip()

            rows_loaded += 1

    db.commit()
    return rows_loaded
