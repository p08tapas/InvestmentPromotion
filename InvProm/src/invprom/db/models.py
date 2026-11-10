from datetime import date, datetime

from sqlalchemy import Boolean, DateTime, Date, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from invprom.db.base import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256))
    sector_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    periods: Mapped[list["FinancialPeriod"]] = relationship(back_populates="company")
    scores: Mapped[list["ScoreSnapshot"]] = relationship(back_populates="company")


class FinancialPeriod(Base):
    __tablename__ = "financial_periods"
    __table_args__ = (UniqueConstraint("company_id", "fy", name="uq_company_fy"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    fy: Mapped[int] = mapped_column(Integer)
    revenue_cr: Mapped[float | None] = mapped_column(Float, nullable=True)
    capex_cr: Mapped[float | None] = mapped_column(Float, nullable=True)
    cash_cr: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_debt_cr: Mapped[float | None] = mapped_column(Float, nullable=True)
    capex_prev_yr_cr: Mapped[float | None] = mapped_column(Float, nullable=True)
    revenue_prev_yr_cr: Mapped[float | None] = mapped_column(Float, nullable=True)
    investments_cr: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_cap_cr: Mapped[float | None] = mapped_column(Float, nullable=True)
    capacity_utilization_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    order_book_cr: Mapped[float | None] = mapped_column(Float, nullable=True)
    order_book_prev_yr_cr: Mapped[float | None] = mapped_column(Float, nullable=True)
    pli_beneficiary: Mapped[bool] = mapped_column(Boolean, default=False)
    management_guidance_hits_12m: Mapped[int] = mapped_column(Integer, default=0)
    odisha_presence: Mapped[bool] = mapped_column(default=False)
    odisha_news_hits_12m: Mapped[int] = mapped_column(Integer, default=0)
    expansion_announcements_12m: Mapped[int] = mapped_column(Integer, default=0)
    source_note: Mapped[str | None] = mapped_column(String(512), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company: Mapped["Company"] = relationship(back_populates="periods")


class ScoreSnapshot(Base):
    __tablename__ = "score_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    model_version: Mapped[str] = mapped_column(String(32))
    sector_fit: Mapped[float] = mapped_column(Float)
    expansion_momentum: Mapped[float] = mapped_column(Float)
    capital_availability: Mapped[float] = mapped_column(Float)
    odisha_affinity: Mapped[float] = mapped_column(Float)
    signal_cash_reserves: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal_management_guidance: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal_capacity_utilization: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal_order_book: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal_government_incentives: Mapped[float | None] = mapped_column(Float, nullable=True)
    ipicol_priority: Mapped[float] = mapped_column(Float)
    tier: Mapped[str] = mapped_column(String(8))
    breakdown_json: Mapped[str] = mapped_column(Text)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    company: Mapped["Company"] = relationship(back_populates="scores")


class NseAnnouncement(Base):
    __tablename__ = "nse_announcements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seq_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    company_name: Mapped[str] = mapped_column(String(256))
    subject: Mapped[str | None] = mapped_column(String(256), nullable=True)
    attachment_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachment_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    sort_date: Mapped[datetime | None] = mapped_column(DateTime, index=True, nullable=True)
    is_expansion: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    mentions_odisha: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_ipicol_relevant: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_management_guidance: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    filing_type: Mapped[str] = mapped_column(String(64), default="corporate_announcement", index=True)
    is_financial_results: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    capex_trigger: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    theme_new_plant: Mapped[bool] = mapped_column(Boolean, default=False)
    theme_capacity_expansion: Mapped[bool] = mapped_column(Boolean, default=False)
    theme_land_acquisition: Mapped[bool] = mapped_column(Boolean, default=False)
    theme_capex_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    theme_fundraising: Mapped[bool] = mapped_column(Boolean, default=False)
    pdf_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pdf_parsed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pdf_parse_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pdf_local_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pdf_text_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    raw_kind: Mapped[str] = mapped_column(String(64), default="corporate-announcements")
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class NseAnnualReport(Base):
    __tablename__ = "nse_annual_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dedupe_key: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    company_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    from_yr: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_yr: Mapped[str | None] = mapped_column(String(16), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    att_file_size: Mapped[str | None] = mapped_column(String(32), nullable=True)
    broadcast_dttm: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class NseCorporateAction(Base):
    __tablename__ = "nse_corporate_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dedupe_key: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    company_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    ex_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    record_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(256), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class NseEvent(Base):
    __tablename__ = "nse_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dedupe_key: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    company_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    event_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    filing_type: Mapped[str] = mapped_column(String(64), default="upcoming_board_meeting")
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class NseSymbolClassifier(Base):
    """NSE official index membership (symbol may appear in multiple indices)."""

    __tablename__ = "nse_symbol_classifiers"
    __table_args__ = (UniqueConstraint("symbol", "classifier_id", name="uq_symbol_classifier"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    classifier_id: Mapped[str] = mapped_column(String(64), index=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class NseListedEquity(Base):
    """All NSE EQ symbols (market-wide tracking scope)."""

    __tablename__ = "nse_listed_equities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    series: Mapped[str] = mapped_column(String(8), default="EQ")
    company_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NseSyncState(Base):
    __tablename__ = "nse_sync_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    feed: Mapped[str] = mapped_column(String(32), unique=True)
    last_to_date: Mapped[date] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
