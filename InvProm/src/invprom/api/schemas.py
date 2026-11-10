from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CompanyScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ticker: str
    name: str
    sector_id: str | None
    fy: int | None
    tier: str
    ipicol_priority: float
    sector_fit: float
    odisha_affinity: float
    signal_cash_reserves: float | None = None
    signal_management_guidance: float | None = None
    signal_capacity_utilization: float | None = None
    signal_order_book: float | None = None
    signal_government_incentives: float | None = None
    expansion_momentum: float = Field(description="Legacy composite: avg(guidance, capacity, order book)")
    capital_availability: float = Field(description="Legacy alias: signal_cash_reserves")
    computed_at: datetime | None


class DossierOut(BaseModel):
    company: CompanyScoreOut
    breakdown: dict


class NseAnnouncementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq_id: str
    symbol: str
    company_name: str
    filing_type: str
    subject: str | None
    attachment_text: str | None
    attachment_url: str | None
    sort_date: datetime | None
    is_expansion: bool
    mentions_odisha: bool
    is_management_guidance: bool
    is_financial_results: bool
    is_ipicol_relevant: bool
    capex_trigger: bool
    theme_new_plant: bool
    theme_capacity_expansion: bool
    theme_land_acquisition: bool
    theme_capex_approval: bool
    theme_fundraising: bool
    pdf_text: str | None = None
    pdf_parse_error: str | None = None
    pdf_parsed_at: datetime | None = None
    pdf_local_path: str | None = None
    pdf_text_path: str | None = None


class NseAnnualReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    company_name: str | None
    from_yr: str | None
    to_yr: str | None
    file_url: str | None
    att_file_size: str | None
    broadcast_dttm: str | None


class NseSyncResultOut(BaseModel):
    feed: str
    from_date: str | None
    to_date: str | None
    fetched: int
    inserted: int
    updated: int
    detail: str | None = None
