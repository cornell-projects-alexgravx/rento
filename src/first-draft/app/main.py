from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.database import create_all_tables
import app.models  # noqa: F401 - ensures all models are registered with SQLAlchemy

from app.routers import (
    users,
    preferences,
    apartments,
    neighborhoods,
    matches,
    agent_logs,
    messages,
    notifications,
)
from app.routers import agents
from app.agents.agent1_image import run_agent1_batch
from app.constants import CORS_ORIGINS


@asynccontextmanager
async def lifespan(application: FastAPI):
    await create_all_tables()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_agent1_batch, "interval", hours=2, id="agent1_batch")
    scheduler.start()
    yield
    scheduler.shutdown()


# ---------------------------------------------------------------------------
# Rate limiter (slowapi) — shared limiter instance used by agent routers.
# OWASP API4:2023 Unrestricted Resource Consumption.
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Rento API",
    description="NYC apartment search automation backend",
    version="1.0.0",
    lifespan=lifespan,
)

# Register the slowapi 429 handler so rate-limit errors return proper JSON.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------------------------
# CORS — restrict to an explicit allow-list instead of "*".
# Read a comma-separated CORS_ORIGINS env var; fall back to localhost:3000.
# OWASP A05:2021 Security Misconfiguration.
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(preferences.router)
app.include_router(apartments.router)
app.include_router(neighborhoods.router)
app.include_router(matches.router)
app.include_router(agent_logs.router)
app.include_router(messages.router)
app.include_router(notifications.router)
app.include_router(agents.router)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}
