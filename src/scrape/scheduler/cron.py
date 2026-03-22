"""
Cron scheduler — powered by APScheduler.

Runs three independent jobs on separate schedules:
  • Craigslist RSS   — every 30 minutes  (configurable)
  • StreetEasy       — every hour
  • Gmail parser     — every 15 minutes

Usage
─────
    python -m apt_agent.scheduler.cron          # run forever (recommended)
    python -m apt_agent.scheduler.cron --once   # run all jobs once and exit

pip install apscheduler
"""

import argparse
import logging
import sys
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from ..config.settings import settings
from ..db.database import init_db
from ..scrapers.craigslist_rss import run_craigslist_scraper
from ..scrapers.streeteasy_zenrows import run_streeteasy_scraper
from ..parsers.gmail_parser import run_gmail_parser
from ..utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Job wrappers  (each catches its own exceptions so one failure doesn't
#                stop the entire scheduler)
# ---------------------------------------------------------------------------

def job_craigslist():
    logger.info("═══ [Craigslist] Job started at %s ═══", datetime.utcnow().isoformat())
    try:
        stats = run_craigslist_scraper()
        logger.info("[Craigslist] Finished — %s", stats)
    except Exception as exc:
        logger.error("[Craigslist] Unhandled exception: %s", exc, exc_info=True)


def job_streeteasy():
    logger.info("═══ [StreetEasy] Job started at %s ═══", datetime.utcnow().isoformat())
    try:
        stats = run_streeteasy_scraper()
        logger.info("[StreetEasy] Finished — %s", stats)
    except Exception as exc:
        logger.error("[StreetEasy] Unhandled exception: %s", exc, exc_info=True)


def job_gmail():
    logger.info("═══ [Gmail] Job started at %s ═══", datetime.utcnow().isoformat())
    try:
        stats = run_gmail_parser()
        logger.info("[Gmail] Finished — %s", stats)
    except Exception as exc:
        logger.error("[Gmail] Unhandled exception: %s", exc, exc_info=True)


# ---------------------------------------------------------------------------
# Scheduler setup
# ---------------------------------------------------------------------------

def build_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone="America/New_York")

    # scheduler.add_job(
    #     job_craigslist,
    #     CronTrigger.from_crontab(settings.CRON_CRAIGSLIST),
    #     id="craigslist",
    #     name="Craigslist RSS",
    #     max_instances=1,
    #     misfire_grace_time=300,
    # )

    # scheduler.add_job(
    #     job_streeteasy,
    #     CronTrigger.from_crontab(settings.CRON_STREETEASY),
    #     id="streeteasy",
    #     name="StreetEasy ZenRows",
    #     max_instances=1,
    #     misfire_grace_time=600,
    # )

    scheduler.add_job(
        job_gmail,
        CronTrigger.from_crontab(settings.CRON_GMAIL),
        id="gmail",
        name="Gmail StreetEasy Emails",
        max_instances=1,
        misfire_grace_time=120,
    )

    return scheduler


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    setup_logging()
    init_db()

    parser = argparse.ArgumentParser(description="Apartment Agent Scheduler")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run all scrapers once immediately, then exit (useful for testing).",
    )
    args = parser.parse_args()

    if args.once:
        logger.info("Running all jobs once (--once mode)…")
        # job_craigslist()
        # job_streeteasy()
        job_gmail()
        logger.info("All jobs finished.")
        sys.exit(0)

    scheduler = build_scheduler()
    logger.info("Scheduler starting — jobs:")
    for job in scheduler.get_jobs():
        logger.info("  %-25s  next run: %s", job.name, job.next_run_time)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()