from __future__ import annotations

BOARD_OUTCOME = "board_meeting_outcome"
INVESTOR_PRESENTATION = "investor_presentation"
FINANCIAL_RESULTS = "financial_results"
ANNUAL_REPORT = "annual_report"
EARNINGS_CALL = "earnings_call_update"
CORPORATE_ANNOUNCEMENT = "corporate_announcement"
PRESS_RELEASE = "press_release"
UPCOMING_BOARD_MEETING = "upcoming_board_meeting"


def filing_type_from_nse_desc(nse_desc: str | None, default: str = CORPORATE_ANNOUNCEMENT) -> str:
    if not nse_desc:
        return default
    mapping = {
        "Outcome of Board Meeting": BOARD_OUTCOME,
        "Investor Presentation": INVESTOR_PRESENTATION,
        "Press Release": PRESS_RELEASE,
        "General Updates": CORPORATE_ANNOUNCEMENT,
        "Integrated Filing- Financial": FINANCIAL_RESULTS,
        "Analysts/Institutional Investor Meet/Con. Call Updates": EARNINGS_CALL,
        "Copy of Newspaper Publication": FINANCIAL_RESULTS,
        "Updates": CORPORATE_ANNOUNCEMENT,
    }
    return mapping.get(nse_desc.strip(), default)


def refine_filing_type(base_type: str, *, is_financial_results_text: bool, override: str | None = None) -> str:
    if override:
        return override
    if is_financial_results_text and base_type == BOARD_OUTCOME:
        return FINANCIAL_RESULTS
    return base_type
