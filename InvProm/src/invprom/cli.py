from __future__ import annotations

import argparse
from pathlib import Path

from invprom.db.session import SessionLocal, init_db
from invprom.ingest.csv_financials import load_financials_csv
from invprom.ingest.nse_retag import retag_all_announcements
from invprom.ingest.nse_sync import backfill_market_filings, sync_all_feeds
from invprom.services.pdf_enrich import enrich_announcement_pdfs
from invprom.services.rescore import rescore_all


def main() -> None:
    parser = argparse.ArgumentParser(description="InvProm local CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db", help="Create SQLite schema")

    imp = sub.add_parser("import-csv", help="Import financial CSV")
    imp.add_argument("path", type=Path)

    sub.add_parser("rescore", help="Recompute all scores")

    nse = sub.add_parser("nse-sync", help="Sync NSE corporate filings feeds (local)")
    nse.add_argument("--days", type=int, default=2)
    nse.add_argument("--no-rescore", action="store_true")

    pdf = sub.add_parser("extract-pdfs", help="Download & parse NSE PDF attachments")
    pdf.add_argument("--limit", type=int, default=15)

    sub.add_parser("nse-retag", help="Re-apply capex/filing tags (fixes newspaper PDF false positives)")

    bf = sub.add_parser("nse-backfill", help="Backfill NSE filings (all listed EQ) for last N days")
    bf.add_argument("--days", type=int, default=30)
    bf.add_argument("--chunk-days", type=int, default=3)

    boot = sub.add_parser("bootstrap", help="Load sample data and rescore")
    boot.add_argument(
        "--csv",
        type=Path,
        default=Path("data/sample_financials.csv"),
    )

    args = parser.parse_args()
    init_db()

    if args.cmd == "init-db":
        print("Database initialized.")
        return

    db = SessionLocal()
    try:
        if args.cmd == "import-csv":
            n = load_financials_csv(db, args.path)
            print(f"Loaded {n} period rows from {args.path}")
        elif args.cmd == "rescore":
            n = rescore_all(db)
            print(f"Scored {n} companies.")
        elif args.cmd == "bootstrap":
            n = load_financials_csv(db, args.csv)
            s = rescore_all(db)
            print(f"Bootstrap: {n} rows, {s} scores.")
        elif args.cmd == "nse-sync":
            results = sync_all_feeds(db, days=args.days)
            for r in results:
                print(
                    f"{r.feed}: {r.from_date}..{r.to_date} "
                    f"fetched={r.fetched} inserted={r.inserted} updated={r.updated}"
                )
            if not args.no_rescore:
                s = rescore_all(db)
                print(f"Rescored {s} companies.")
        elif args.cmd == "extract-pdfs":
            stats = enrich_announcement_pdfs(db, limit=args.limit)
            print(stats)
        elif args.cmd == "nse-retag":
            stats = retag_all_announcements(db)
            print(stats)
        elif args.cmd == "nse-backfill":
            results = backfill_market_filings(db, days=args.days, chunk_days=args.chunk_days)
            for r in results:
                print(
                    f"{r.feed}: fetched={r.fetched} inserted={r.inserted} updated={r.updated} "
                    f"{r.detail or ''}"
                )
    finally:
        db.close()


if __name__ == "__main__":
    main()
