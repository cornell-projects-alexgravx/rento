"""
StreetEasy Email Ingestion Pipeline
====================================
Entry-point that ties GmailFetcher → StreetEasyEmailParser → ListingWriter
together into a single callable pipeline.

Run from the command line:
    python pipeline.py                         # fetch & ingest latest emails
    python pipeline.py --eml path/to/test.eml  # parse a local .eml file (for testing)
    python pipeline.py --after 2026/03/01      # only emails received after this date

Environment variables:
    GMAIL_CREDENTIALS_PATH   path to credentials.json (default: credentials.json)
    GMAIL_TOKEN_PATH         path to token.json (default: token.json)
    DATABASE_URL             SQLAlchemy connection string
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run_pipeline(
    eml_path: str | None = None,
    after_date: str | None = None,
    max_results: int = 50,
) -> None:
    """
    Execute the full ingestion pipeline.

    Parameters
    ----------
    eml_path:
        If set, parse a single local .eml file instead of calling the Gmail API.
        Useful for testing / replaying messages.
    after_date:
        Only fetch Gmail messages after this date (YYYY/MM/DD format).
    max_results:
        Maximum number of Gmail messages to fetch per run.
    """
    from streeteasy_email import StreetEasyEmailParser

    parser = StreetEasyEmailParser()

    # ── Step 1: Collect raw message dicts ────────────────────────────────────
    if eml_path:
        logger.info("Offline mode — parsing local file: %s", eml_path)
        listings = parser.parse_eml_file(eml_path)
    else:
        from gmail_fetcher import GmailFetcher

        fetcher = GmailFetcher(
            credentials_path=os.environ.get("GMAIL_CREDENTIALS_PATH", "credentials.json"),
            token_path=os.environ.get("GMAIL_TOKEN_PATH", "token.json"),
        )
        raw_messages = fetcher.fetch_new_messages(
            max_results=max_results, after_date=after_date
        )

        # ── Step 2: Parse each email ──────────────────────────────────────────
        listings = []
        for msg in raw_messages:
            listings.extend(parser.parse_gmail_message(msg))

    logger.info("Total listings parsed: %d", len(listings))
    if not listings:
        logger.info("Nothing to write. Exiting.")
        return

    # ── Step 3: Write to the database ─────────────────────────────────────────
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error(
            "DATABASE_URL environment variable is not set. "
            "Cannot write to the database."
        )
        # In offline / test mode, just print the parsed listings instead.
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
    import json

    print("\n" + "=" * 60)
    print(f"  {len(listings)} listing(s) parsed")
    print("=" * 60)
    for i, listing in enumerate(listings, 1):
        d = asdict(listing)
        print(f"\n[{i}] {listing.name}")
        for k, v in d.items():
            if v not in (None, "", [], False):
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
        help="Only fetch Gmail messages after this date.",
    )
    p.add_argument(
        "--max-results",
        type=int,
        default=50,
        metavar="N",
        help="Maximum number of Gmail messages to fetch (default: 50).",
    )
    return p


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    run_pipeline(
        eml_path=args.eml,
        after_date=args.after,
        max_results=args.max_results,
    )