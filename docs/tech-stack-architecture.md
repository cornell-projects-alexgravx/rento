# Tech Stack & Architecture

## Tech Stack

| Layer | Technology | Version | Role |
|-------|-----------|---------|------|
| Frontend | React | 18 | SPA framework |
| Frontend | TypeScript | — | Type safety |
| Frontend | Vite | — | Dev server and bundler |
| Frontend | Tailwind CSS | — | Utility-first styling |
| Frontend | Zustand | — | Global state management (auth, listings, agent status, notifications) |
| Frontend | React Router | — | Client-side routing (`/onboarding`, `/dashboard`) |
| Backend | Python | 3.11 | Runtime (per Dockerfile `python:3.11-slim`) |
| Backend | FastAPI | — | Async REST API framework |
| Backend | SQLAlchemy | — | Async ORM (via `asyncpg` driver) |
| Backend | asyncpg | — | Async PostgreSQL driver |
| Backend | Pydantic | v2 | Request/response schema validation |
| Backend | APScheduler | — | Background job scheduling (Agent 1 batch every 2 hours) |
| Backend | slowapi | — | Rate limiting (OWASP API4 protection) |
| Backend | bcrypt | — | Password hashing (direct, no passlib) |
| Backend | PyJWT | — | JWT generation and validation (HS256, 7-day expiry) |
| AI | Claude Sonnet 4.6 | `claude-sonnet-4-6` | Vision (Agent 1), text ranking (Agent 2), email drafting (Agent 3) |
| AI | LangGraph | — | State machine framework for all three agents |
| AI | Anthropic Python SDK | — | Async Claude client (`anthropic.AsyncAnthropic`) |
| Database | PostgreSQL | 16 | Primary data store |
| Email | Mailpit | latest | Local SMTP server + web UI for dev |
| Infra | Docker Compose | — | Local multi-container orchestration |
| Data | Craigslist scraper | — | Custom parser (`backend/parsers/craigslist_scraper.py`) |
| Data | StreetEasy scraper | — | Custom parser (`backend/parsers/streeteasy_scraper.py`) |

## System Architecture

The system runs as four Docker containers orchestrated by Docker Compose:

- **`frontend`** — Vite-built React SPA served on port 5173. Communicates with the API exclusively via REST calls to `http://api:8000` (internal) or `http://localhost:8000` (browser). Polls agent status and notifications every 15 seconds.
- **`api`** — FastAPI application on port 8000. Exposes two router layers: legacy routers at root paths and the canonical `v1` layer at `/api/v1`. Handles auth, listings, preferences, negotiations, notifications, tours, and agent control. Triggers AI agents as background tasks.
- **`db`** — PostgreSQL 16 on port 5432 with a named volume `pgdata` for data persistence. The API connects via asyncpg using `postgresql+asyncpg://...`.
- **`mailpit`** — Local SMTP server on port 1025 (SMTP) + port 8025 (web UI). Agent 3 sends all outbound emails through it in development.

The API container also runs APScheduler in-process, which fires the Agent 1 batch job every 2 hours to analyze new apartment images.

All API routes under `/api/v1` require a JWT Bearer token (except `POST /auth/register` and `POST /auth/login`). Tokens are signed with HS256 and expire after 7 days (configurable via `JWT_EXPIRE_HOURS`).

## Component Responsibilities

### Frontend

Two pages:
- **Onboarding** (`/onboarding`) — multi-step form collecting housing requirements, negotiation preferences, and notification settings. On completion, triggers `POST /api/v1/listings/run-filter` to populate matches.
- **Dashboard** (`/dashboard`) — two tabs:
  - **Match** — listing cards with match scores, negotiation status, and like/dislike actions. Filters and sorts by price, score, commute time, and status.
  - **Agent Log** — live log stream from all three agents, filterable by phase and level.

Global state (Zustand store) tracks: authentication, current user, listings, active negotiations, agent status, and notifications.

### Backend API

Organised into two layers:
- **Legacy routers** (root prefix) — `users`, `apartments`, `preferences`, `matches`, `messages`, `notifications`, `neighborhoods`, `agent_logs`, `agents`. Present for internal/dev use.
- **v1 routers** (`/api/v1` prefix) — the primary API consumed by the frontend: `auth`, `listings`, `preferences`, `negotiations`, `agent`, `notifications`, `tours`.

All v1 routes use the `get_current_user` FastAPI dependency for JWT validation.

### AI Agents

All three agents are implemented as LangGraph `StateGraph` compiled graphs. Each agent creates its own `AsyncSession` via `async_session_factory`.

| Agent | Trigger | Steps | External calls |
|-------|---------|-------|----------------|
| **Agent 1 — Image Analysis** | APScheduler (every 2 hrs) or per-apartment `POST /agents/run-agent1/{id}` | fetch apartment → call Claude Vision (base64 images) → persist labels | Claude Vision API |
| **Agent 2 — Semantic Matching** | `POST /api/v1/listings/run-scoring` or per-user endpoint | fetch user context → fetch matches → batch Claude ranking → persist scores | Claude Text API |
| **Agent 3 — Autonomous Negotiation** | `POST /api/v1/negotiations` (background task) | fetch context → draft email → send via SMTP → poll for host reply → analyze reply → loop (max 5 rounds) → generate ICS on acceptance | Claude Text API, SMTP |

### Data Layer

PostgreSQL 16 accessed via SQLAlchemy async ORM. Tables are created via `create_all_tables()` called at FastAPI startup. No migration tool (e.g., Alembic) is in use — schema is managed via `Base.metadata.create_all`.

## Data Flow

**New user completing onboarding:**
1. User fills preferences in the Onboarding page → `PUT /api/v1/preferences/housing`, `/negotiation`, `/notifications` persist to the four preference tables.
2. On completion, frontend calls `POST /api/v1/listings/run-filter` → backend compares `ObjectivePreferences` against all `Apartment` rows, inserts `Match` rows for qualifying apartments.
3. Backend immediately runs `recalculate_all_match_scores` (Agent 2 logic) so listings show match percentages on first load.

**Listing scored and displayed:**
1. Separately, APScheduler calls `run_agent1_batch` every 2 hours → finds apartments with empty `image_labels` → for each, calls Claude Vision → stores labels on `Apartment`.
2. Agent 2 reads image labels + user profile → calls Claude for 0–10 scores → normalizes to 0.0–1.0 → stores on `Match.match_score`.
3. Frontend `GET /api/v1/listings` retrieves apartments joined with match data, applies filters/sorts, and renders listing cards with scores and negotiation status.

**Negotiation started:**
1. User clicks "Negotiate" on a listing → `POST /api/v1/negotiations` → sets `Match.status = "in_progress"` → triggers Agent 3 as a background task.
2. Agent 3 calls Claude to draft an opening email proposing 3 visit slots → sends via Mailpit SMTP → inserts `Message(type="agent")` row.
3. Agent 3 polls every 30 minutes (default) for a `Message(type="host")` row (host replies are injected via dev endpoint or real SMTP inbound).
4. On each reply, Claude classifies it as `accepted / counter_offer / rejected / no_reply`. If counter, drafts a new email and loops (up to 5 rounds).
5. On acceptance, Agent 3 generates an ICS calendar file, emails it to the host, sets `Match.status = "completed"`, and creates a `Notification` row.
6. Frontend polls `/agent/status` and `/notifications` every 15 seconds, displaying the outcome to the user.
