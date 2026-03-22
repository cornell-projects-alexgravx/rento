"""Centralised configuration constants.

All environment variable reads happen here. Every other module imports
from this file instead of calling ``os.getenv`` directly.

``load_dotenv()`` is called once at import time so that a local ``.env``
file is picked up in development without any extra setup.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# ── Database ───────────────────────────────────────────────────────────────────

DATABASE_HOST: str = os.getenv("DATABASE_HOST", "localhost")
POSTGRES_USER: str = os.getenv("POSTGRES_USER", "rento")
POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "")
POSTGRES_DB: str = os.getenv("POSTGRES_DB", "rento")

DATABASE_URL: str = (
    f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{DATABASE_HOST}:5432/{POSTGRES_DB}"
)

# ── Anthropic ──────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY: str | None = os.getenv("ANTHROPIC_API_KEY")

# ── SMTP ───────────────────────────────────────────────────────────────────────

SMTP_HOST: str = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT: int = int(os.getenv("SMTP_PORT", "1025"))
SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "false").lower() == "true"
SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM: str = os.getenv("SMTP_FROM", "rento@localhost")

# ── CORS ───────────────────────────────────────────────────────────────────────

CORS_ORIGINS: list[str] = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

# ── Security ───────────────────────────────────────────────────────────────────

DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

# ── Agent 3 ────────────────────────────────────────────────────────────────────

AGENT3_MAX_ROUNDS: int = int(os.getenv("AGENT3_MAX_NEGOTIATION_ROUNDS", "5"))
AGENT3_POLL_INTERVAL_S: int = int(os.getenv("AGENT3_REPLY_POLL_INTERVAL_SECONDS", "1800"))
