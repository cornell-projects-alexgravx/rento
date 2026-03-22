"""
StreetEasy Email Ingestion Pipeline
====================================
Entry-point that ties together:

  GmailFetcher  →  StreetEasyEmailParser  →  ListingScraper (ZenRows)  →  ListingWriter

Run from the command line:
    python pipeline.py                            # fetch emails, scrape listings, write to DB
    python pipeline.py --eml path/to/test.eml     # parse a local .eml file
    python pipeline.py --after 2026/03/01         # only emails received after this date
    python pipeline.py --no-scrape                # skip ZenRows scraping step

Environment variables:
    GMAIL_CREDENTIALS_PATH   path to credentials.json      (default: credentials.json)
    GMAIL_TOKEN_PATH         path to token.json            (default: token.json)
    ZENROWS_API_KEY          ZenRows API key               (required unless --no-scrape)
    DATABASE_URL             SQLAlchemy connection string   (optional; prints to stdout if unset)
"""

from __future__ import annotations

import argparse
import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run_pipeline(
    eml_path: str | None = None,
    after_date: str | None = None,
    max_results: int = 50,
    scrape: bool = True,
    zenrows_api_key: str | None = None,
) -> None:
    """
    Execute the full ingestion pipeline.

    Parameters
    ----------
    eml_path:
        Parse a local .eml file instead of calling the Gmail API.
    after_date:
        Only fetch Gmail messages after this date (YYYY/MM/DD).
    max_results:
        Maximum number of Gmail messages to fetch per run.
    scrape:
        If True, each listing is enriched via ZenRows after email parsing.
    zenrows_api_key:
        ZenRows API key. Falls back to the ZENROWS_API_KEY env var.
    """
    from streeteasy_email import StreetEasyEmailParser

    email_parser = StreetEasyEmailParser()

    # -- Step 1: Collect listings from email(s) --------------------------------
    if eml_path:
        logger.info("Offline mode -- parsing local file: %s", eml_path)
        listings = email_parser.parse_eml_file(eml_path)
    else:
        from gmail_fetcher import GmailFetcher

        fetcher = GmailFetcher(
            credentials_path=os.environ.get("GMAIL_CREDENTIALS_PATH", "credentials.json"),
            token_path=os.environ.get("GMAIL_TOKEN_PATH", "token.json"),
        )
        raw_messages = fetcher.fetch_new_messages(
            max_results=max_results, after_date=after_date
        )
        listings = []
        for msg in raw_messages:
            listings.extend(email_parser.parse_gmail_message(msg))

    logger.info("Listings from email parsing: %d", len(listings))
    if not listings:
        logger.info("Nothing to process. Exiting.")
        return

    # -- Step 2: Enrich each listing by scraping its StreetEasy page -----------
    if scrape:
        api_key = zenrows_api_key or os.environ.get("ZENROWS_API_KEY", "")
        if not api_key:
            logger.warning(
                "ZENROWS_API_KEY is not set -- skipping scraping step. "
                "Set the env var or pass --zenrows-api-key to enable enrichment."
            )
        else:
            from listing_scraper import ListingScraper

            scraper = ListingScraper(zenrows_api_key=api_key)
            logger.info("Enriching %d listing(s) via ZenRows...", len(listings))
            listings = scraper.enrich_batch(listings)
    else:
        logger.info("Scraping disabled (--no-scrape). Skipping enrichment step.")

    # -- Step 3: Write to the database -----------------------------------------
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.warning(
            "DATABASE_URL is not set -- printing parsed listings to stdout instead."
        )
        _print_listings(listings)
        return

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from db_writer import ListingWriter

    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)

    with Session() as session:
        writer = ListingWriter(session)
        created, skipped = writer.upsert_listings(listings)

    logger.info("Pipeline complete. Created=%d, Skipped=%d", created, skipped)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_listings(listings) -> None:
    """Pretty-print listings to stdout (used when DB is unavailable)."""
    from dataclasses import asdict

    print("\n" + "=" * 65)
    print(f"  {len(listings)} listing(s)")
    print("=" * 65)
    for i, listing in enumerate(listings, 1):
        d = asdict(listing)
        print(f"\n[{i}] {listing.name}  ({listing.bedroom_type})  ${listing.price:,}/mo")
        for k, v in d.items():
            if k in ("name", "bedroom_type", "price"):
                continue
            if v not in (None, "", [], False, 0):
                print(f"    {k}: {v}")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Ingest StreetEasy alert emails into the apartment database."
    )
    p.add_argument(
        "--eml",
        metavar="PATH",
        help="Parse a local .eml file instead of calling the Gmail API.",
    )
    p.add_argument(
        "--after",
        metavar="YYYY/MM/DD",
        help="Only fetch Gmail messages received after this date.",
    )
    p.add_argument(
        "--max-results",
        type=int,
        default=50,
        metavar="N",
        help="Maximum number of Gmail messages to fetch (default: 50).",
    )
    p.add_argument(
        "--no-scrape",
        action="store_true",
        help="Skip the ZenRows scraping step (email data only).",
    )
    p.add_argument(
        "--zenrows-api-key",
        metavar="KEY",
        help="ZenRows API key (overrides the ZENROWS_API_KEY env var).",
    )
    return p


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    run_pipeline(
        eml_path=args.eml,
        after_date=args.after,
        max_results=args.max_results,
        scrape=not args.no_scrape,
        zenrows_api_key=args.zenrows_api_key,
    )