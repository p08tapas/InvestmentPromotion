"""Lightweight SQLite migrations for local MVP (add columns without Alembic)."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

FINANCIAL_PERIOD_COLS = {
    "investments_cr": "FLOAT",
    "market_cap_cr": "FLOAT",
    "capacity_utilization_pct": "FLOAT",
    "order_book_cr": "FLOAT",
    "order_book_prev_yr_cr": "FLOAT",
    "pli_beneficiary": "BOOLEAN DEFAULT 0",
    "management_guidance_hits_12m": "INTEGER DEFAULT 0",
}

SCORE_SNAPSHOT_COLS = {
    "signal_cash_reserves": "FLOAT",
    "signal_management_guidance": "FLOAT",
    "signal_capacity_utilization": "FLOAT",
    "signal_order_book": "FLOAT",
    "signal_government_incentives": "FLOAT",
}

NSE_ANNOUNCEMENT_COLS = {
    "is_management_guidance": "BOOLEAN DEFAULT 0",
    "filing_type": "VARCHAR(64) DEFAULT 'corporate_announcement'",
    "is_financial_results": "BOOLEAN DEFAULT 0",
    "capex_trigger": "BOOLEAN DEFAULT 0",
    "theme_new_plant": "BOOLEAN DEFAULT 0",
    "theme_capacity_expansion": "BOOLEAN DEFAULT 0",
    "theme_land_acquisition": "BOOLEAN DEFAULT 0",
    "theme_capex_approval": "BOOLEAN DEFAULT 0",
    "theme_fundraising": "BOOLEAN DEFAULT 0",
    "pdf_text": "TEXT",
    "pdf_page_count": "INTEGER",
    "pdf_parsed_at": "DATETIME",
    "pdf_parse_error": "VARCHAR(512)",
    "pdf_local_path": "VARCHAR(512)",
    "pdf_text_path": "VARCHAR(512)",
}

NSE_EVENT_COLS = {
    "filing_type": "VARCHAR(64) DEFAULT 'upcoming_board_meeting'",
}


def _existing_columns(engine: Engine, table: str) -> set[str]:
    insp = inspect(engine)
    return {c["name"] for c in insp.get_columns(table)} if insp.has_table(table) else set()


def _add_columns(engine: Engine, table: str, columns: dict[str, str]) -> None:
    if not inspect(engine).has_table(table):
        return
    existing = _existing_columns(engine, table)
    with engine.begin() as conn:
        for name, sql_type in columns.items():
            if name in existing:
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))


def run_migrations(engine: Engine) -> None:
    _add_columns(engine, "financial_periods", FINANCIAL_PERIOD_COLS)
    _add_columns(engine, "score_snapshots", SCORE_SNAPSHOT_COLS)
    _add_columns(engine, "nse_announcements", NSE_ANNOUNCEMENT_COLS)
    _add_columns(engine, "nse_events", NSE_EVENT_COLS)
