from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from invprom.db.models import Company, FinancialPeriod
from invprom.scoring.metrics import net_cash_cr, net_cash_to_market_cap, order_book_growth


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / abs(previous)


@dataclass
class ScoreResult:
    sector_fit: float
    odisha_affinity: float
    signal_cash_reserves: float
    signal_management_guidance: float
    signal_capacity_utilization: float
    signal_order_book: float
    signal_government_incentives: float
    ipicol_priority: float
    tier: str
    breakdown: dict[str, Any]
    # Legacy API fields (mapped from signals)
    expansion_momentum: float
    capital_availability: float


def _tier(priority: float, cash: float, guidance: float) -> str:
    if priority >= 70 and (cash >= 55 or guidance >= 55):
        return "A"
    if priority >= 52:
        return "B"
    return "C"


def _score_cash_reserves(period: FinancialPeriod) -> tuple[float, dict[str, Any]]:
    nc = net_cash_cr(period.cash_cr, period.investments_cr, period.total_debt_cr)
    ratio = net_cash_to_market_cap(nc, period.market_cap_cr)
    rev_g = _pct_change(period.revenue_cr, period.revenue_prev_yr_cr)

    parts: list[float] = []
    if ratio is not None and ratio > 0:
        parts.append(_clamp(25.0 + min(ratio / 0.25, 1.0) * 55.0))
    elif nc is not None and nc > 0:
        parts.append(_clamp(40.0 + min(nc / 5000.0, 1.0) * 40.0))
    else:
        parts.append(25.0)

    # High surplus + modest revenue growth → deployment candidate (banker heuristic)
    if ratio is not None and ratio >= 0.12 and rev_g is not None and rev_g < 0.15:
        parts.append(85.0)
    elif ratio is not None and ratio >= 0.08:
        parts.append(70.0)

    score = sum(parts) / len(parts)
    meta = {
        "net_cash_cr": nc,
        "net_cash_to_market_cap": ratio,
        "revenue_growth_yoy": rev_g,
    }
    return round(score, 2), meta


def _score_management_guidance(period: FinancialPeriod) -> tuple[float, dict[str, Any]]:
    guidance_hits = period.management_guidance_hits_12m or 0
    expansion_hits = period.expansion_announcements_12m or 0
    combined = guidance_hits + 0.5 * expansion_hits
    score = _clamp(20.0 + min(combined, 8) * 10.0)
    return round(score, 2), {
        "management_guidance_hits_12m": guidance_hits,
        "expansion_announcements_12m": expansion_hits,
    }


def _score_capacity_utilization(period: FinancialPeriod, *, track: bool) -> tuple[float, dict[str, Any]]:
    util = period.capacity_utilization_pct
    if not track or util is None:
        return 50.0, {"capacity_utilization_pct": util, "applicable": track, "note": "n/a for sector type"}
    if util >= 90:
        score = _clamp(75.0 + (util - 90) * 3.0)
    elif util >= 80:
        score = 65.0
    elif util >= 60:
        score = 45.0
    else:
        score = 30.0
    return round(score, 2), {"capacity_utilization_pct": util, "applicable": True}


def _score_order_book(period: FinancialPeriod, *, track: bool) -> tuple[float, dict[str, Any]]:
    growth = order_book_growth(period.order_book_cr, period.order_book_prev_yr_cr)
    if not track:
        return 45.0, {"order_book_growth_yoy": growth, "applicable": False}
    if growth is None:
        return 40.0, {"order_book_growth_yoy": None, "applicable": True}
    score = _clamp(35.0 + min(max(growth, 0) / 0.4, 1.0) * 55.0)
    return round(score, 2), {"order_book_growth_yoy": growth, "applicable": True}


def _score_government_incentives(
    company: Company,
    period: FinancialPeriod,
    incentive_keywords: list[str],
) -> tuple[float, dict[str, Any]]:
    score = 35.0
    if period.pli_beneficiary:
        score += 45.0
    text = " ".join(filter(None, [company.name, company.description or "", company.sector_id or ""])).lower()
    kw_hits = sum(1 for kw in incentive_keywords if kw in text)
    score += min(kw_hits, 4) * 5.0
    if company.sector_id in {"electronics_mfg", "renewables_green"}:
        score += 10.0
    return round(_clamp(score), 2), {
        "pli_beneficiary": period.pli_beneficiary,
        "incentive_keyword_hits": kw_hits,
    }


def compute_scores(
    company: Company,
    period: FinancialPeriod,
    sector_keywords: list[str],
    *,
    track_capacity: bool = True,
    track_order_book: bool = False,
    incentive_keywords: list[str] | None = None,
) -> ScoreResult:
    text = " ".join(filter(None, [company.name, company.description or "", company.sector_id or ""]))
    text_lower = text.lower()
    keyword_hits = sum(1 for kw in sector_keywords if kw in text_lower)
    sector_fit = _clamp(40.0 + min(keyword_hits, 5) * 12.0) if company.sector_id else 35.0
    if company.sector_id:
        sector_fit = max(sector_fit, 50.0)

    affinity = 20.0
    if period.odisha_presence:
        affinity += 40.0
    affinity += min(period.odisha_news_hits_12m, 5) * 8.0
    odisha_affinity = _clamp(affinity)

    cash, cash_meta = _score_cash_reserves(period)
    guidance, guidance_meta = _score_management_guidance(period)
    capacity, capacity_meta = _score_capacity_utilization(period, track=track_capacity)
    orders, orders_meta = _score_order_book(period, track=track_order_book)
    incentives, incentive_meta = _score_government_incentives(
        company, period, incentive_keywords or []
    )

    weights = {
        "signal_cash_reserves": 0.14,
        "signal_management_guidance": 0.14,
        "signal_capacity_utilization": 0.14,
        "signal_order_book": 0.14,
        "signal_government_incentives": 0.14,
        "sector_fit": 0.3,
    }

    ipicol_priority = (
        weights["signal_cash_reserves"] * cash
        + weights["signal_management_guidance"] * guidance
        + weights["signal_capacity_utilization"] * capacity
        + weights["signal_order_book"] * orders
        + weights["signal_government_incentives"] * incentives
        + weights["sector_fit"] * sector_fit
    )
    tier = _tier(ipicol_priority, cash, guidance)

    breakdown = {
        "framework": "investment_banker_capex_signals_v2",
        "company_ticker": company.ticker,
        "fy": period.fy,
        "signals": {
            "1_cash_reserves": {"score": cash, **cash_meta},
            "2_management_guidance": {"score": guidance, **guidance_meta},
            "3_capacity_utilization": {"score": capacity, **capacity_meta},
            "4_order_book_growth": {"score": orders, **orders_meta},
            "5_government_incentives": {"score": incentives, **incentive_meta},
        },
        "wbidc_targeting": {
            "sector_fit": sector_fit,
            "regional_affinity": odisha_affinity,
            "state_presence": period.odisha_presence,
            "regional_mentions_12m": period.odisha_news_hits_12m,
        },
        "weights": weights,
    }

    legacy_expansion = round((guidance + capacity + orders) / 3.0, 2)

    return ScoreResult(
        sector_fit=round(sector_fit, 2),
        odisha_affinity=round(odisha_affinity, 2),
        signal_cash_reserves=cash,
        signal_management_guidance=guidance,
        signal_capacity_utilization=capacity,
        signal_order_book=orders,
        signal_government_incentives=incentives,
        ipicol_priority=round(ipicol_priority, 2),
        tier=tier,
        breakdown=breakdown,
        expansion_momentum=legacy_expansion,
        capital_availability=cash,
    )


def breakdown_to_json(result: ScoreResult) -> str:
    return json.dumps(asdict(result), ensure_ascii=False)
