from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


@asynccontextmanager
async def lifespan(application: FastAPI):
    await create_all_tables()
    yield


app = FastAPI(
    title="Rento API",
    description="NYC apartment search automation backend",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}
