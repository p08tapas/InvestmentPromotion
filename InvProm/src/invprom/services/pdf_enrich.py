from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from invprom.config import settings
from invprom.db.models import NseAnnouncement
from invprom.ingest.pdf_text import download_and_extract_pdf

PRIORITY_FILING_TYPES = {
    "board_meeting_outcome",
    "investor_presentation",
    "financial_results",
    "press_release",
    "corporate_announcement",
}


def _should_extract(row: NseAnnouncement) -> bool:
    if not row.attachment_url:
        return False
    if row.pdf_text and not row.pdf_parse_error:
        return False
    if not row.attachment_url.lower().split("?")[0].endswith(".pdf"):
        return False
    return row.capex_trigger or row.filing_type in PRIORITY_FILING_TYPES or row.is_ipicol_relevant


def _save_pdf_artifacts(seq_id: str, pdf_bytes: bytes | None, text: str | None) -> tuple[str | None, str | None]:
    cache = settings.pdf_cache_dir
    cache.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() else "_" for c in seq_id)[:80]
    pdf_rel: str | None = None
    txt_rel: str | None = None
    if pdf_bytes:
        pdf_file = cache / f"{safe}.pdf"
        pdf_file.write_bytes(pdf_bytes)
        pdf_rel = str(pdf_file.relative_to(settings.data_dir)).replace("\\", "/")
    if text:
        txt_file = cache / f"{safe}.txt"
        txt_file.write_text(text, encoding="utf-8")
        txt_rel = str(txt_file.relative_to(settings.data_dir)).replace("\\", "/")
    return pdf_rel, txt_rel


def retag_from_text(row: NseAnnouncement) -> None:
    from invprom.ingest.nse_retag import refine_filing_type_for_row, retag_announcement

    retag_announcement(row)


def enrich_announcement_pdfs(db: Session, *, limit: int = 15) -> dict[str, int | str]:
    """
    Download PDFs from NSE into data/pdf_cache/, extract text into DB + .txt files.
    """
    q = (
        db.query(NseAnnouncement)
        .filter(NseAnnouncement.attachment_url.is_not(None))
        .order_by(NseAnnouncement.sort_date.desc())
    )
    candidates = [r for r in q.limit(limit * 5).all() if _should_extract(r)][:limit]

    processed = 0
    ok = 0
    failed = 0
    retagged = 0
    cache_dir = str(settings.pdf_cache_dir.resolve())

    for row in candidates:
        processed += 1
        result = download_and_extract_pdf(row.attachment_url or "")
        row.pdf_parsed_at = datetime.utcnow()
        if result.error:
            row.pdf_parse_error = result.error[:512]
            failed += 1
        else:
            row.pdf_text = result.text or None
            row.pdf_page_count = result.page_count
            row.pdf_parse_error = None
            pdf_rel, txt_rel = _save_pdf_artifacts(row.seq_id, result.pdf_bytes, result.text)
            row.pdf_local_path = pdf_rel
            row.pdf_text_path = txt_rel
            ok += 1
            before = row.capex_trigger
            retag_from_text(row)
            if row.capex_trigger and not before:
                retagged += 1

    db.commit()
    return {
        "queued": len(candidates),
        "processed": processed,
        "ok": ok,
        "failed": failed,
        "new_capex_triggers": retagged,
        "pdf_cache_dir": cache_dir,
        "note": "PDFs saved under data/pdf_cache/; text also in SQLite nse_announcements.pdf_text",
    }
