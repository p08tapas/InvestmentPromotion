from __future__ import annotations

import re
from dataclasses import dataclass

from invprom.ingest.nse_capex_themes import CapexThemes, tag_capex_themes

# Signal 2 — management guidance (filings, presentations, outcome of board meeting)
MANAGEMENT_GUIDANCE = re.compile(
    r"\b(evaluating expansion|expansion opportunit|planned capex|capex of\s|capital expenditure of|"
    r"land acquisition|capacity utilization|approaching\s+9\d\s*%|"
    r"greenfield|brownfield|new plant|new facility|debottleneck|"
    r"invest(?:ment)?\s+of\s+(?:rs\.?|inr|₹)|over next\s+\d+\s+years)\b",
    re.I,
)

CAPEX_KEYWORDS = re.compile(
    r"\b(capex|capital expenditure|greenfield|brownfield|capacity expansion|new plant|new unit|"
    r"debottleneck|project cost|setting up|commencement of commercial production|"
    r"invest(?:ment)?\s+of\s+(?:rs\.?|inr)|expansion project)\b",
    re.I,
)

WEST_BENGAL_KEYWORDS = re.compile(
    r"\bwest bengal|kolkata|calcutta|howrah|haldia|asansol|durgapur|kharagpur|"
    r"siliguri|jalpaiguri|bardhaman|purba|medinipur|salt lake|rajarhat|"
    r"shrirampur|tamluk|electronic complex\b",
    re.I,
)

# Signal 5 — incentives / policy-led capex language
GOVERNMENT_INCENTIVE = re.compile(
    r"\b(pli\b|production linked incentive|semiconductor|fab\b|green hydrogen|"
    r"advanced chemistry cell|data cent(?:er|re)|solar module|battery manufacturing)\b",
    re.I,
)

INVESTMENT_PROMOTION_RELEVANT = re.compile(
    r"\b(outcome of board meeting|press release|investor presentation|corporate presentation|"
    r"earnings call|conference call|analyst meet|capacity expansion|new plant|commencement|project|mou|joint venture)\b",
    re.I,
)


@dataclass(frozen=True)
class NseTags:
    is_expansion: bool
    mentions_odisha: bool
    is_management_guidance: bool
    is_government_incentive: bool
    is_ipicol_relevant: bool
    themes: CapexThemes


@dataclass(frozen=True)
class AnnouncementTag:
    title: str
    is_expansion: bool
    mentions_odisha: bool


def tag_nse_text(*parts: str | None) -> NseTags:
    """Tag from announcement fields. Pass attachment, NSE subject/desc, symbol; optional pdf last."""
    text = " ".join(p for p in parts if p)
    themes = tag_capex_themes(text)
    guidance = bool(MANAGEMENT_GUIDANCE.search(text)) or themes.any_trigger
    expansion = bool(CAPEX_KEYWORDS.search(text)) or guidance or themes.any_trigger
    promo_doc = bool(INVESTMENT_PROMOTION_RELEVANT.search(text)) or themes.is_financial_results
    return NseTags(
        is_expansion=expansion,
        mentions_odisha=bool(WEST_BENGAL_KEYWORDS.search(text)),
        is_management_guidance=guidance,
        is_government_incentive=bool(GOVERNMENT_INCENTIVE.search(text)),
        is_ipicol_relevant=promo_doc or expansion,
        themes=themes,
    )
