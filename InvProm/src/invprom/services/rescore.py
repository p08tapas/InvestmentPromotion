from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from invprom.config import settings
from invprom.db.models import Company, FinancialPeriod, ScoreSnapshot
from invprom.scoring.engine import compute_scores
from invprom.services.nse_pipeline import ensure_pipeline_companies_from_nse


def _load_sector_meta(sector_id: str | None, taxonomy_path: Path) -> tuple[list[str], bool, bool]:
    if not sector_id or not taxonomy_path.is_file():
        return [], True, False
    data = json.loads(taxonomy_path.read_text(encoding="utf-8"))
    for sector in data.get("sectors", []):
        if sector.get("id") == sector_id:
            return (
                list(sector.get("keywords", [])),
                bool(sector.get("track_capacity_utilization", True)),
                bool(sector.get("track_order_book", False)),
            )
    return [], True, False


def _load_incentive_keywords(path: Path) -> list[str]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    keywords: list[str] = []
    for item in data.get("incentive_sectors", []):
        keywords.extend(item.get("keywords", []))
    return keywords


def rescore_all(db: Session) -> int:
    ensure_pipeline_companies_from_nse(db)
    taxonomy_path = settings.sector_taxonomy_path
    incentives_path = settings.government_incentives_path
    model_version = settings.score_model_version
    incentive_keywords = _load_incentive_keywords(incentives_path)
    count = 0

    companies = db.query(Company).all()
    for company in companies:
        period = (
            db.query(FinancialPeriod)
            .filter(FinancialPeriod.company_id == company.id)
            .order_by(FinancialPeriod.fy.desc())
            .first()
        )
        if period is None:
            continue

        keywords, track_capacity, track_order_book = _load_sector_meta(company.sector_id, taxonomy_path)
        result = compute_scores(
            company,
            period,
            keywords,
            track_capacity=track_capacity,
            track_order_book=track_order_book,
            incentive_keywords=incentive_keywords,
        )

        db.add(
            ScoreSnapshot(
                company_id=company.id,
                model_version=model_version,
                sector_fit=result.sector_fit,
                expansion_momentum=result.expansion_momentum,
                capital_availability=result.capital_availability,
                odisha_affinity=result.odisha_affinity,
                signal_cash_reserves=result.signal_cash_reserves,
                signal_management_guidance=result.signal_management_guidance,
                signal_capacity_utilization=result.signal_capacity_utilization,
                signal_order_book=result.signal_order_book,
                signal_government_incentives=result.signal_government_incentives,
                ipicol_priority=result.ipicol_priority,
                tier=result.tier,
                breakdown_json=json.dumps(result.breakdown, ensure_ascii=False),
            )
        )
        count += 1

    db.commit()
    return count
