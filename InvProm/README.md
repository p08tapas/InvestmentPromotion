# Investment Promotion Intelligence Platform (local MVP) — WBIDC

Prioritize **national companies** for West Bengal investment outreach (WBIDC) using **five capex-deployment signals** investment bankers track, plus **sector fit**—no GO SWIFT, no paid data vendor, runs **locally**.

See **[docs/SIGNALS.md](docs/SIGNALS.md)** for the full framework.

| # | Signal | Primary inputs |
|---|--------|----------------|
| 1 | Large cash reserves | Net cash, net cash / market cap (CSV) |
| 2 | Management guidance | NSE/BSE text + `management_guidance_hits_12m` |
| 3 | Capacity utilization | `capacity_utilization_pct` (manufacturing) |
| 4 | Order book growth | Order book YoY (EPC/defense/cap goods) |
| 5 | Government incentives | `pli_beneficiary` + `government_incentives.json` |

## What this MVP does

1. **Company universe** via CSV (includes exemplars: TCS, L&T, BEL, etc.).
2. **Banker metrics** from annual reports / research notes.
3. **NSE corporate announcements** auto-tagged for guidance & capex language.
4. **Pipeline API** (`GET /api/pipeline`) with per-signal scores and Tier A/B/C.
5. **Framework doc endpoint**: `GET /api/framework/signals`.

## NSE corporate filings (capex document tracking)

Mirrors [NSE Corporate Filings & Actions](https://www.nseindia.com/companies-listing/corporate-filings-actions). See **[docs/NSE_FILINGS.md](docs/NSE_FILINGS.md)**.

| Document | Ingestion |
|----------|-----------|
| Board meeting outcomes | `subject=Outcome of Board Meeting` |
| Investor presentations | `subject=Investor Presentation` |
| Financial results | Board outcomes + text classification |
| Earnings / call updates | `subject=Analysts/Institutional Investor Meet/Con. Call Updates` |
| Annual reports | Per-symbol `/api/annual-reports` for your CSV universe |

**Auto-tagged capex themes:** new plant · capacity expansion · land acquisition · capex approval · fundraising

```powershell
invprom nse-sync --days 2
```

**Market-wide:** ~2,000+ NSE EQ symbols loaded via `POST /api/nse/sync` (universe step) or `POST /api/nse/backfill?days=30`.

**API:** `POST /api/nse/sync?days=3` · `POST /api/nse/backfill?days=30` · `GET /api/nse/history?days=30` · `GET /api/nse/history/grouped` · `GET /api/nse/classifiers` · `GET /api/nse/filings`

**PDF extraction:** pulls text from NSE PDF links (board outcomes, presentations) and re-runs capex theme tagging.

```powershell
invprom extract-pdfs --limit 15
```

Downloads go to **`data/pdf_cache/{seq_id}.pdf`** and **`data/pdf_cache/{seq_id}.txt`**; full text is also in SQLite `nse_announcements.pdf_text`. View paths in the filing **View** modal after extract.

## What it does *not* do yet

- No GO SWIFT, GO PLUS, or govt SSO (by design for now).
- No licensed financial terminal for P&L/balance sheet—**CSV** still supplies revenue/capex/cash unless you add AR parsing later.

## Data strategy without a vendor

| Field | Where IPICOL staff get it |
|-------|---------------------------|
| Revenue, capex, cash, debt | Listed co **annual report** (Notes: PPE/capex, cash & bank, borrowings) |
| Prior-year comparatives | Previous AR or same CSV row columns |
| Expansion count | Count of relevant **BSE/NSE announcements** (12 months)—manual or scripted |
| Odisha affinity | `odisha_presence` (unit in state), news mentions, past IPICOL meeting notes |
| Sector | Map to `data/sector_taxonomy.json` `sector_id` |

Template: `data/sample_financials.csv`

Later phases (still no vendor): PDF table extractor for AR, BSE corp announcement HTML export, bulk XBRL from MCA for top accounts.

## Quick start (Windows)

```powershell
cd D:\InvProm
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
invprom bootstrap
uvicorn invprom.main:app --reload --app-dir src
```

Open **http://127.0.0.1:8000/ui** (HTML dashboard) or http://127.0.0.1:8000/docs

- `POST /api/bootstrap/sample-data` — load demo companies
- `GET /api/pipeline?tier=A` — prioritized list
- `GET /api/companies/RELIANCE` — dossier with score breakdown
- `POST /api/ingest/csv` — upload your workbook export

## CLI

```powershell
invprom import-csv D:\path\to\your_financials.csv
invprom rescore
```

## Configuration

Copy `.env.example` to `.env`:

- `INVPROM_DATABASE_URL=sqlite:///./data/invprom.db`
- `INVPROM_SCORE_MODEL_VERSION=ipicol-v1`

Edit `data/sector_taxonomy.json` with Odisha focus sectors and keywords.

## Scoring (transparent)

Weights: 30% sector fit, 30% expansion, 20% capital, 20% Odisha affinity.

Tiers:

- **A** — high priority + strong sector fit + expansion or cash signal  
- **B** — moderate fit for roadshow invites  
- **C** — watchlist  

Full breakdown returned per company (`breakdown_json`).

## Suggested IPICOL workflow (local)

1. **Monthly**: interns/analysts update CSV from ARs for target universe (start 100–200 names).
2. **Import + rescore** on a shared laptop or IPICOL LAN server.
3. Export pipeline via API or future CSV export UI.
4. Promotion team uses dossier talking points; meetings logged in a simple spreadsheet until CRM v2.

## Project layout

```
src/invprom/
  main.py              # FastAPI
  ingest/csv_financials.py
  ingest/nse_announcements.py  # optional
  scoring/engine.py
  services/rescore.py
data/
  sector_taxonomy.json
  sample_financials.csv
```

## Compliance note

Use only public filings and internally recorded outreach notes. Scores are **decision support**, not clearance or incentive decisions.
