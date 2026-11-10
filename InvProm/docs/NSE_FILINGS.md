# NSE corporate filings ingestion (IPICOL)

Source page: [NSE Corporate Filings & Corporate Actions](https://www.nseindia.com/companies-listing/corporate-filings-actions)

## What NSE exposes (no vendor)

| Document type on site | How InvProm ingests |
|------------------------|---------------------|
| **Corporate announcements** | `/api/corporate-announcements` with `subject=` filters |
| **Board meeting outcomes** | Subject: `Outcome of Board Meeting` |
| **Investor presentations** | Subject: `Investor Presentation` |
| **Financial results** | Board outcomes + text match “financial results”; subject `Integrated Filing- Financial` |
| **Earnings / analyst call updates** | Subject: `Analysts/Institutional Investor Meet/Con. Call Updates` |
| **Annual reports** | `/api/annual-reports?symbol=` per tracked ticker |
| **Upcoming board / result dates** | `/api/event-calendar` |

Configure subjects in `data/nse_subject_feeds.json`.

## Capex triggers auto-tagged in text

| Theme | Example language |
|-------|------------------|
| `new_plant` | New unit, greenfield manufacturing |
| `capacity_expansion` | Capacity addition, debottleneck |
| `land_acquisition` | Land acquisition, industrial land |
| `capex_approval` | Capex of ₹…, board approved project |
| `fundraising` | QIP, preferential allotment, ECB |

## API usage

```http
POST /api/nse/sync?days=3
GET  /api/nse/filings?filing_type=board_meeting_outcome
GET  /api/nse/capex-triggers?theme=land_acquisition
GET  /api/nse/annual-reports?symbol=TCS
```

## Suggested daily job (local PC)

```powershell
invprom nse-sync --days 2
```

Use `POST /api/nse/sync?full_announcements=true&days=1` only when you need the **full** feed (very large JSON).

## Future enhancements

- PDF text extract from `attchmntFile` for deeper capex amounts
- BSE mirror for dual-listed names
- Match triggers to Odisha geography in attachment body
