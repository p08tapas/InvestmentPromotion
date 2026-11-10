from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from invprom.db.models import Company, FinancialPeriod, NseAnnouncement, NseListedEquity


def _company_name_for_symbol(db: Session, symbol: str) -> str:
    eq = db.query(NseListedEquity).filter(NseListedEquity.symbol == symbol).one_or_none()
    if eq and eq.company_name:
        return eq.company_name[:256]
    ann = (
        db.query(NseAnnouncement.company_name)
        .filter(NseAnnouncement.symbol == symbol)
        .order_by(NseAnnouncement.sort_date.desc())
        .first()
    )
    if ann and ann.company_name:
        return ann.company_name[:256]
    return symbol


def ensure_pipeline_companies_from_nse(db: Session, *, since_days: int = 365) -> int:
    """
  Ensure every NSE symbol with recent capex/guidance activity has a Company + FinancialPeriod
  so rescore can rank the full market, not only CSV-seeded names.
  """
    cutoff = datetime.utcnow() - timedelta(days=since_days)
    symbols = {
        str(s).upper()
        for (s,) in db.query(NseAnnouncement.symbol)
        .filter(
            NseAnnouncement.sort_date.is_not(None),
            NseAnnouncement.sort_date >= cutoff,
            or_(
                NseAnnouncement.capex_trigger.is_(True),
                NseAnnouncement.is_management_guidance.is_(True),
                NseAnnouncement.is_expansion.is_(True),
            ),
        )
        .distinct()
        .all()
    }
    if not symbols:
        return 0

    fy = date.today().year
    created = 0
    for symbol in sorted(symbols):
        company = db.query(Company).filter(Company.ticker == symbol).one_or_none()
        if company is None:
            company = Company(ticker=symbol, name=_company_name_for_symbol(db, symbol))
            db.add(company)
            db.flush()
            db.add(
                FinancialPeriod(
                    company_id=company.id,
                    fy=fy,
                    source_note="NSE filing signals (extend with CSV for balance-sheet fields)",
                )
            )
            created += 1
            continue
        period = (
            db.query(FinancialPeriod)
            .filter(FinancialPeriod.company_id == company.id)
            .order_by(FinancialPeriod.fy.desc())
            .first()
        )
        if period is None:
            db.add(
                FinancialPeriod(
                    company_id=company.id,
                    fy=fy,
                    source_note="NSE filing signals (extend with CSV for balance-sheet fields)",
                )
            )
            created += 1

    if created:
        db.commit()
    return created
