"""
Centralised settings — all values must be set in .env (see .env.example).

This file defines only the shape of the config: field names, types,
and safe non-sensitive defaults (log level, page limits, cron schedules).
No credentials, URLs, or secrets live here.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List


class Settings(BaseSettings):
    # ── Database ──────────────────────────────────────────────────────────
    DATABASE_URL: str                       # required — no default
    DB_ECHO: bool = False

    # ── ZenRows ───────────────────────────────────────────────────────────
    ZENROWS_API_KEY: str                    # required — no default

    # ── Gmail ─────────────────────────────────────────────────────────────
    GMAIL_CREDENTIALS_FILE: str            # required — no default
    GMAIL_TOKEN_FILE: str = "token.json"   # safe default — not a secret
    GMAIL_SEARCH_QUERY: str                # required — your specific query

    # ── Craigslist RSS ────────────────────────────────────────────────────
    # Comma-separated list of RSS URLs defined entirely in .env
    CRAIGSLIST_RSS_URLS: List[str]         # required — no default
    CRAIGSLIST_MAX_ITEMS: int = 50

    # ── StreetEasy ────────────────────────────────────────────────────────
    STREETEASY_SEARCH_URL: str             # required — your search URL
    STREETEASY_MAX_PAGES: int = 5

    # ── Scheduler ─────────────────────────────────────────────────────────
    CRON_CRAIGSLIST: str = "*/30 * * * *"
    CRON_STREETEASY: str = "0 * * * *"
    CRON_GMAIL:      str = "*/15 * * * *"

    # ── Geocoding ─────────────────────────────────────────────────────────
    GEOCODE_ENABLED: bool = True

    # ── Logging ───────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str  = "apt_agent.log"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()