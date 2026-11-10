from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from invprom.config import settings
from invprom.db.models import NseSymbolClassifier

ARCHIVES_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) InvProm-WBIDC/0.1",
    "Referer": "https://www.nseindia.com/",
}


def _load_classifier_config(path: Path) -> dict:
    if not path.is_file():
        return {"base_url": "", "classifiers": []}
    return json.loads(path.read_text(encoding="utf-8"))


def sync_nse_index_classifiers(db: Session) -> dict[str, int]:
    cfg = _load_classifier_config(settings.nse_index_classifiers_path)
    base = (cfg.get("base_url") or "").rstrip("/") + "/"
    inserted = 0
    failed = 0

    with httpx.Client(timeout=45.0, follow_redirects=True, headers=ARCHIVES_HEADERS) as client:
        for item in cfg.get("classifiers", []):
            cid = item.get("id")
            csv_name = item.get("csv")
            if not cid or not csv_name:
                continue
            url = base + csv_name
            try:
                response = client.get(url)
                response.raise_for_status()
            except httpx.HTTPError:
                failed += 1
                continue

            reader = csv.DictReader(io.StringIO(response.text))
            symbols: set[str] = set()
            for row in reader:
                sym = (row.get("Symbol") or row.get("symbol") or "").strip().upper()
                if sym:
                    symbols.add(sym)

            db.query(NseSymbolClassifier).filter(NseSymbolClassifier.classifier_id == cid).delete()
            for sym in symbols:
                db.add(NseSymbolClassifier(symbol=sym, classifier_id=cid))
                inserted += 1
            db.flush()

    db.commit()
    return {"classifier_rows": inserted, "classifiers_failed": failed}


def classifier_catalog(path: Path | None = None) -> list[dict[str, str]]:
    cfg = _load_classifier_config(path or settings.nse_index_classifiers_path)
    return [
        {"id": c["id"], "label": c.get("label", c["id"])}
        for c in cfg.get("classifiers", [])
    ]
