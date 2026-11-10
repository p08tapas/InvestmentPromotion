from __future__ import annotations

import re

from sqlalchemy.orm import Session

from invprom.db.models import NseAnnouncement
from invprom.ingest.nse_filing_classifier import filing_type_from_nse_desc, refine_filing_type
from invprom.ingest.nse_sync import _apply_tags_to_row
from invprom.ingest.nse_tags import tag_nse_text

# NSE subject / headline patterns where PDFs are often full newspaper pages or boilerplate —
# do not use PDF body for capex theme detection (high false-positive rate).
SKIP_PDF_THEME_SUBJECTS = re.compile(
    r"\b("
    r"copy of newspaper publication|newspaper publication|"
    r"loss of share certificate|duplicate share certificate|"
    r"trading window|closure of trading window|"
    r"record date|book closure|"
    r"compliance certificate|reg\s*30\s*compliance|"
    r"change in director|resignation of|appointment of (?:director|auditor)|"
    r"intimation of loss|shareholding pattern|"
    r"disclosure under regulation\s*29"
    r")\b",
    re.I,
)

NEWSPAPER_RESULTS = re.compile(r"\b(newspaper publication)\b", re.I)


def text_parts_for_tagging(
    *,
    attachment_text: str | None,
    subject: str | None,
    symbol: str | None = None,
    pdf_text: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Return (attachment, subject, pdf?) — pdf dropped for routine compliance filings."""
    subj = (subject or "").strip()
    if subj and SKIP_PDF_THEME_SUBJECTS.search(subj):
        return attachment_text, subject, None
    headline = " ".join(filter(None, [attachment_text, subject]))
    if SKIP_PDF_THEME_SUBJECTS.search(headline):
        return attachment_text, subject, None
    return attachment_text, subject, pdf_text


def tag_filing(
    *,
    attachment_text: str | None,
    subject: str | None,
    symbol: str | None = None,
    pdf_text: str | None = None,
):
    a, s, p = text_parts_for_tagging(
        attachment_text=attachment_text,
        subject=subject,
        symbol=symbol,
        pdf_text=pdf_text,
    )
    parts: list[str | None] = [a, s, symbol]
    if p:
        parts.append(p)
    return tag_nse_text(*parts)


def refine_filing_type_for_row(
    subject: str | None,
    tags,
    override: str | None = None,
) -> str:
    base = filing_type_from_nse_desc(subject)
    if override:
        return override
    if subject and NEWSPAPER_RESULTS.search(subject):
        return "financial_results"
    return refine_filing_type(base, is_financial_results_text=tags.themes.is_financial_results, override=None)


def retag_announcement(row: NseAnnouncement, *, filing_type_override: str | None = None) -> bool:
    tags = tag_filing(
        attachment_text=row.attachment_text,
        subject=row.subject,
        symbol=row.symbol,
        pdf_text=row.pdf_text,
    )
    filing_type = refine_filing_type_for_row(row.subject, tags, override=filing_type_override)
    before = (
        row.capex_trigger,
        row.theme_capacity_expansion,
        row.theme_new_plant,
        row.filing_type,
    )
    _apply_tags_to_row(row, tags, filing_type)
    after = (
        row.capex_trigger,
        row.theme_capacity_expansion,
        row.theme_new_plant,
        row.filing_type,
    )
    return before != after


def retag_all_announcements(db: Session) -> dict[str, int]:
    changed = 0
    total = 0
    for row in db.query(NseAnnouncement).yield_per(200):
        total += 1
        if retag_announcement(row):
            changed += 1
    db.commit()
    from invprom.services.capex_metrics import reconcile_capex_trigger_flags

    reconciled = reconcile_capex_trigger_flags(db)
    return {"processed": total, "changed": changed, "capex_flags_reconciled": reconciled}
