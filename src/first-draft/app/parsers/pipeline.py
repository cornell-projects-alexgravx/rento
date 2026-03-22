"""
StreetEasy Email Ingestion Pipeline
====================================
Entry-point that ties together:

  GmailFetcher → StreetEasyEmailParser → ListingScraper (ZenRows) → ListingWriter

Fully async — uses your app's async_session_factory (asyncpg) for all DB writes.

Run from the command line (from project root):
    python -m app.parsers.pipeline                        # fetch emails, scrape, write to DB
    python -m app.parsers.pipeline --eml path/to/test.eml # parse a local .eml file
    python -m app.parsers.pipeline --after 2026/03/01     # emails received after this date
    python -m app.parsers.pipeline --no-scrape            # skip ZenRows scraping step

Environment variables (in .env or shell):
    GMAIL_CREDENTIALS_PATH   path to credentials.json      (default: credentials.json)
    GMAIL_TOKEN_PATH         path to token.json            (default: token.json)
    ZENROWS_API_KEY          ZenRows API key               (required unless --no-scrape)
    ANTHROPIC_API_KEY        Anthropic API key             (optional, enables Claude gap-fill)
    DATABASE_URL             set in app/database.py via .env
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def run_pipeline(
    eml_path: str | None = None,
    after_date: str | None = None,
    max_results: int = 50,
    scrape: bool = True,
    zenrows_api_key: str | None = None,
) -> None:
    """Execute the full ingestion pipeline (async)."""

    from app.parsers.streeteasy_email import StreetEasyEmailParser

    email_parser = StreetEasyEmailParser()

    # ── Step 1: Collect listings from email(s) ────────────────────────────────
    if eml_path:
        logger.info("Offline mode — parsing local file: %s", eml_path)
        listings = email_parser.parse_eml_file(eml_path)
    else:
        from app.parsers.gmail_fetcher import GmailFetcher

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

    # ── Step 2: Enrich each listing by scraping its StreetEasy page ──────────
    # (ListingScraper is sync/blocking — runs fine in an async context as it
    # uses the requests library, not asyncio. For production at scale you could
    # wrap it in asyncio.to_thread(); for this pipeline it's fine as-is.)
    if scrape:
        api_key = zenrows_api_key or os.environ.get("ZENROWS_API_KEY", "")
        if not api_key:
            logger.warning(
                "ZENROWS_API_KEY not set — skipping scraping step."
            )
        else:
            from app.parsers.listing_scraper import ListingScraper

            scraper = ListingScraper(
                zenrows_api_key=api_key,
                anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
            )
            logger.info("Enriching %d listing(s) via ZenRows...", len(listings))
            # Run the blocking scraper in a thread so we don't block the event loop
            listings = await asyncio.to_thread(scraper.enrich_batch, listings)
    else:
        logger.info("Scraping disabled (--no-scrape).")

    # ── Step 3: Write to the database (async) ─────────────────────────────────
    from app.database import async_session_factory
    from app.parsers.db_writer import ListingWriter

    async with async_session_factory() as session:
        writer = ListingWriter(session)
        created, skipped = await writer.upsert_listings(listings)

    logger.info("Pipeline complete. Created=%d, Skipped=%d", created, skipped)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_listings(listings) -> None:
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
    p.add_argument("--eml", metavar="PATH",
                   help="Parse a local .eml file instead of calling the Gmail API.")
    p.add_argument("--after", metavar="YYYY/MM/DD",
                   help="Only fetch Gmail messages received after this date.")
    p.add_argument("--max-results", type=int, default=50, metavar="N",
                   help="Maximum number of Gmail messages to fetch (default: 50).")
    p.add_argument("--no-scrape", action="store_true",
                   help="Skip the ZenRows scraping step (email data only).")
    p.add_argument("--zenrows-api-key", metavar="KEY",
                   help="ZenRows API key (overrides ZENROWS_API_KEY env var).")
    return p


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    asyncio.run(
        run_pipeline(
            eml_path=args.eml,
            after_date=args.after,
            max_results=args.max_results,
            scrape=not args.no_scrape,
            zenrows_api_key=args.zenrows_api_key,
        )
    )