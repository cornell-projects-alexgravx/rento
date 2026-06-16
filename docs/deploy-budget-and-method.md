# Deployment & Budget

## Deployment Method

**Current: Local Docker Compose**

All services run in Docker containers orchestrated by `docker-compose.yml` in the project root. There is no production deployment configured. All containers are built from source or pulled from Docker Hub at `docker compose up`.

## Infrastructure Components

| Component | Image / Source | Port(s) | Notes |
|-----------|---------------|---------|-------|
| PostgreSQL | `postgres:16` | `5432` | Data persisted in named volume `pgdata` |
| Mailpit | `axllent/mailpit` | `1025` (SMTP), `8025` (Web UI) | Local SMTP server + email inspector |
| FastAPI Backend | Built from `./backend/Dockerfile` (python:3.11-slim) | `8000` | Waits for `db` health check before starting |
| React Frontend | Built from `./frontend/Dockerfile` | `5173` | Waits for `api` health check before starting |

**Startup order:** `db` → (health check: `pg_isready`) → `mailpit` → `api` → (health check: `GET /health`) → `frontend`

## Environment Variables

Create a `.env` file in the project root (copy `.env.example`):

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key for all three Claude agents |
| `POSTGRES_DB` | Yes | PostgreSQL database name (default: `rento`) |
| `POSTGRES_USER` | Yes | PostgreSQL username (default: `rento`) |
| `POSTGRES_PASSWORD` | Yes | PostgreSQL password |
| `JWT_SECRET` | Yes | Secret for signing JWT tokens (change from default in production) |
| `SMTP_HOST` | No | SMTP host (default: `localhost`; Docker sets to `mailpit`) |
| `SMTP_PORT` | No | SMTP port (default: `1025`) |
| `SMTP_USE_TLS` | No | Enable TLS for SMTP (default: `false`) |
| `SMTP_USERNAME` | No | SMTP auth username (not needed for Mailpit) |
| `SMTP_PASSWORD` | No | SMTP auth password (not needed for Mailpit) |
| `SMTP_FROM` | No | From address for outbound emails (default: `rento@localhost`) |
| `CORS_ORIGINS` | No | Comma-separated allowed origins (default: `http://localhost:3000,http://localhost:5173`) |
| `JWT_EXPIRE_HOURS` | No | JWT expiry in hours (default: `168` = 7 days) |
| `AGENT3_MAX_NEGOTIATION_ROUNDS` | No | Max counter-offer rounds for Agent 3 (default: `5`) |
| `AGENT3_REPLY_POLL_INTERVAL_SECONDS` | No | Seconds between host-reply polls (default: `1800` = 30 min) |
| `DEBUG` | No | Enable debug mode (default: `false`) |

## Running Locally

```bash
# 1. Clone the repository
git clone https://github.com/cornell-projects-alexgravx/rento.git
cd rento

# 2. Create environment file
cp .env.example .env
# Edit .env and set: ANTHROPIC_API_KEY, POSTGRES_PASSWORD, JWT_SECRET

# 3. Start all services
docker compose up -d

# 4. Seed initial data (optional — populates neighborhoods and sample listings)
docker compose exec api python scripts/seed.py
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Mailpit Web UI | http://localhost:8025 |

## Production Deployment

No production deployment has been configured for this project (built for a hackathon demo). When deploying to production, the main considerations are:

- Replace Mailpit with a real SMTP provider (e.g., SendGrid, AWS SES, Postmark).
- Set `JWT_SECRET` to a cryptographically random value.
- Set `DEBUG=false` and restrict `CORS_ORIGINS` to your actual frontend domain.
- Use a managed PostgreSQL service (e.g., AWS RDS, Supabase, Render Postgres) instead of the Docker container to ensure data persistence.
- The `AGENT3_REPLY_POLL_INTERVAL_SECONDS` default (1800s) is appropriate for production; the APScheduler Agent 1 batch (every 2 hours) is in-process and will need review if the API is scaled horizontally.

Suitable platforms for deploying the API and frontend as-is: Render, Railway, Fly.io, or AWS ECS.

## Estimated Monthly Cost (Production)

Assumes modest production traffic (single region, ~50 active users, moderate Claude API usage).

| Service | Provider Example | Tier | Est. Cost/mo |
|---------|-----------------|------|-------------|
| Backend (FastAPI) | Render Web Service | Starter (512 MB RAM) | ~$7 |
| Frontend (React) | Render Static Site or Vercel | Free tier | $0 |
| PostgreSQL | Render Postgres | Starter (1 GB) | ~$7 |
| Claude API (Agent 1) | Anthropic | ~500 image batches/mo × 5 images | ~$5–15 |
| Claude API (Agent 2) | Anthropic | ~200 ranking calls/mo | ~$3–8 |
| Claude API (Agent 3) | Anthropic | ~100 negotiations × 3 rounds avg | ~$5–15 |
| SMTP (production) | SendGrid | Free tier (100 emails/day) | $0 |
| Domain + SSL | Any registrar | — | ~$1–2 |

**Total estimate:** ~$28–55/month

Claude API costs are the main variable. Heavy usage (many simultaneous negotiations, large apartment datasets) could push the total to $100–150/month. Image analysis (Agent 1) cost scales with the number of new listings ingested per batch cycle.
