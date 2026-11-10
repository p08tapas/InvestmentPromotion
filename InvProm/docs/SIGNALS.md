# Capex deployment signals (investment-banker framework)

InvProm scores companies on **five leading indicators** that investors and investment bankers use before capex cycles—plus **Odisha sector fit** and **local affinity** for IPICOL outreach.

## Signal 1 — Large cash reserves (deployment capacity)

Not cash alone:

**Net cash (₹ cr)** = Cash & bank + Current investments − Total debt  

**Net cash / market cap** = deployable surplus relative to equity value

High net cash with **moderate organic growth** often precedes expansion, M&A, buybacks, or new strategic investments.

**Data:** Annual report / exchange financials → CSV columns `cash_cr`, `investments_cr`, `total_debt_cr`, `market_cap_cr`.

## Signal 2 — Management guidance

Leading language in filings and calls, e.g.:

- “Evaluating expansion opportunities”
- “Capex of ₹X crore over next 2 years”
- “Land acquisition underway”
- “Capacity utilization approaching 90%”

**Data:** NSE/BSE announcements (auto-tagged), investor presentations; optional manual `management_guidance_hits_12m` in CSV.

## Signal 3 — Capacity utilization

| Utilization | Typical read |
|-------------|----------------|
| ~60% | Little urgent capex |
| 90–95% | Expansion likely |

**Data:** Analyst notes or AR segment → `capacity_utilization_pct` (manufacturing sectors only).

## Signal 4 — Order book growth

Relevant for **defense, EPC, capital goods, infrastructure**.

**Order book growth** = (Order book − Prior order book) / Prior order book

**Data:** `order_book_cr`, `order_book_prev_yr_cr` where disclosed.

## Signal 5 — Government incentives

PLI and allied schemes (semiconductors, electronics, green hydrogen, EV batteries, renewables, data centers, etc.) often coincide with large project announcements.

**Data:** `pli_beneficiary` flag + `government_incentives.json` sector/keyword match + NSE text.

## IPICOL composite score

| Component | Weight |
|-----------|--------|
| Signal 1–5 (each) | 11% (55% total) |
| Odisha sector fit | 22.5% |
| Odisha affinity | 22.5% |

Tiers **A / B / C** rank who to approach for greenfield/brownfield investment in Odisha **before** they commit elsewhere.
