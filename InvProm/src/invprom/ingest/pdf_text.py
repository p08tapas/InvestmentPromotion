from __future__ import annotations

import io
import re
from dataclasses import dataclass

import httpx

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-actions",
}

MAX_PDF_BYTES = 12 * 1024 * 1024
MAX_PAGES = 20
MAX_TEXT_CHARS = 80_000


@dataclass
class PdfExtractResult:
    text: str
    page_count: int
    pdf_bytes: bytes | None = None
    error: str | None = None


def _normalize_whitespace(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_text_from_pdf_bytes(data: bytes, *, max_pages: int = MAX_PAGES) -> PdfExtractResult:
    if fitz is None:
        return PdfExtractResult("", 0, error="pymupdf not installed")
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        return PdfExtractResult("", 0, error=f"open failed: {exc}")

    parts: list[str] = []
    page_count = min(len(doc), max_pages)
    try:
        for i in range(page_count):
            page = doc.load_page(i)
            parts.append(page.get_text("text"))
    finally:
        doc.close()

    text = _normalize_whitespace("\n".join(parts))[:MAX_TEXT_CHARS]
    return PdfExtractResult(text=text, page_count=page_count, pdf_bytes=data)


def download_and_extract_pdf(url: str, *, timeout_s: float = 45.0) -> PdfExtractResult:
    if not url or not url.lower().split("?")[0].endswith(".pdf"):
        return PdfExtractResult("", 0, error="not a pdf url")

    try:
        with httpx.Client(timeout=timeout_s, follow_redirects=True, headers=NSE_HEADERS) as client:
            response = client.get(url)
            response.raise_for_status()
            data = response.content
    except httpx.HTTPError as exc:
        return PdfExtractResult("", 0, error=f"download failed: {exc}")

    if len(data) > MAX_PDF_BYTES:
        return PdfExtractResult("", 0, error="pdf too large")

    return extract_text_from_pdf_bytes(data)
