# API Design

## Base URL

```
http://localhost:8000/api/v1
```

Interactive docs: `http://localhost:8000/docs`

## Authentication

JWT Bearer tokens. All v1 routes require the header:

```
Authorization: Bearer <token>
```

Tokens are signed with HS256, expire after 7 days (default), and are issued by `/auth/register` and `/auth/login`.

---

## Endpoints

### Auth

#### `POST /auth/register`
Create a new user account.

**Auth required:** No

**Request body:**
```json
{
  "email": "string — valid email address",
  "password": "string — plain text (hashed with bcrypt before storage)",
  "name": "string — display name"
}
```

**Response `201`:**
```json
{
  "token": "string — JWT access token",
  "user": {
    "id": "string — UUID",
    "name": "string",
    "email": "string",
    "onboardingComplete": "boolean — true if ObjectivePreferences row exists"
  }
}
```

**Error responses:**
- `409` — Email already registered

---

#### `POST /auth/login`
Authenticate and receive a token.

**Auth required:** No

**Request body:**
```json
{
  "email": "string",
  "password": "string"
}
```

**Response `200`:**
```json
{
  "token": "string — JWT access token",
  "user": {
    "id": "string",
    "name": "string",
    "email": "string",
    "onboardingComplete": "boolean"
  }
}
```

**Error responses:**
- `401` — Invalid email or password

---

#### `GET /auth/me`
Return the current authenticated user.

**Auth required:** Yes

**Response `200`:**
```json
{
  "id": "string",
  "name": "string",
  "email": "string",
  "onboardingComplete": "boolean"
}
```

---

### Listings

#### `GET /listings`
Paginated, filtered, sorted list of apartments enriched with match data for the current user.

**Auth required:** Yes

**Query parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | int | 1 | Page number (≥1) |
| `pageSize` | int | 20 | Items per page (1–100) |
| `negotiationStatus` | string | — | Filter by `pending \| negotiating \| accepted` |
| `matchType` | string | — | Filter by `perfect \| flex` (perfect = score ≥ 0.22) |
| `status` | string | — | Filter by listing status (`available`) |
| `minPrice` | int | — | Minimum monthly rent |
| `maxPrice` | int | — | Maximum monthly rent |
| `minScore` | float | — | Minimum match score (0.0–1.0) |
| `sortBy` | string | — | `price \| matchScore \| commuteMinutes` |
| `sortOrder` | string | `desc` | `asc \| desc` |

**Response `200`:**
```json
{
  "items": [
    {
      "id": "string",
      "title": "string — apartment name",
      "address": "string — neighborhood + NYC",
      "neighborhood": "string | null",
      "price": "integer — monthly rent",
      "bedrooms": "string — bedroom type enum value",
      "pets": "boolean",
      "parking": ["string"],
      "laundry": ["string"],
      "images": ["string — image URLs"],
      "imageLabels": ["string — style labels from Agent 1"],
      "lat": "float | null",
      "lng": "float | null",
      "availableFrom": "string | null — ISO date",
      "leaseLength": "integer | null — months",
      "matchScore": "float | null — 0.0 to 1.0",
      "matchReasoning": "string | null — one-sentence Claude explanation",
      "negotiationStatus": "string | null — pending | negotiating | accepted",
      "commuteMinutes": "integer | null",
      "matchId": "string | null — Match row ID",
      "matchType": "string — perfect | flex",
      "status": "string — available",
      "hostEmail": "string | null",
      "hostPhone": "string | null"
    }
  ],
  "total": "integer — total matching items before pagination",
  "page": "integer",
  "pageSize": "integer"
}
```

---

#### `GET /listings/{listing_id}`
Single listing with match data.

**Auth required:** Yes

**Response `200`:** Same shape as a single item in `GET /listings`.

**Error responses:**
- `404` — Listing not found

---

#### `POST /listings/run-filter`
Run the objective filter for the current user — creates `Match` rows for qualifying apartments and auto-runs scoring.

**Auth required:** Yes

**Request body:** None

**Response `200`:**
```json
{
  "matched": "integer — number of new Match rows created",
  "message": "string — summary message"
}
```

---

#### `POST /listings/run-scoring`
Recalculate AI match scores for all Match rows belonging to the current user (calls Agent 2 logic).

**Auth required:** Yes

**Request body:** None

**Response `200`:**
```json
{
  "scored": "integer — number of matches scored",
  "message": "string"
}
```

---

#### `POST /listings/{listing_id}/react`
Like or dislike a listing. Like creates a Match row; dislike deletes it.

**Auth required:** Yes

**Request body:**
```json
{
  "action": "string — like | dislike"
}
```

**Response `200`:**
```json
{
  "matchId": "string | null — Match row ID (null on dislike)",
  "action": "string — like | dislike"
}
```

**Error responses:**
- `400` — Invalid action value
- `404` — Listing not found

---

### Preferences

#### `GET /preferences`
Return the current user's full preference set.

**Auth required:** Yes

**Response `200`:**
```json
{
  "housing": {
    "bedroomType": "string | null",
    "selectedAreas": ["string"],
    "minBudget": "integer | null",
    "maxBudget": "integer | null",
    "moveInDate": "string | null — ISO date",
    "leaseLengthMonths": "integer | null",
    "laundry": ["string"],
    "parking": ["string"],
    "pets": "boolean",
    "workLatitude": "float | null",
    "workLongitude": "float | null",
    "commuteMethod": "string | null — drive | transit | bike",
    "maxCommuteMinutes": "integer | null"
  },
  "negotiation": {
    "enableAutomation": "boolean",
    "negotiableItems": ["string"],
    "goals": ["string"],
    "maxRent": "integer | null",
    "maxDeposit": "integer | null",
    "latestMoveInDate": "string | null — ISO date",
    "minLeaseMonths": "integer | null",
    "maxLeaseMonths": "integer | null",
    "negotiationStyle": "string | null — polite | professional | assertive | friendly"
  },
  "notifications": {
    "enableNotifications": "boolean",
    "autoScheduling": "boolean",
    "notificationTypes": ["string"],
    "frequency": "string — realtime | daily | weekly"
  }
}
```

---

#### `PUT /preferences/housing`
Update housing preferences (partial update — only provided fields are changed).

**Auth required:** Yes

**Request body:** Any subset of the `housing` fields from `GET /preferences`.

**Response `200`:** Updated housing preferences object.

---

#### `PUT /preferences/negotiation`
Update negotiation preferences (partial update).

**Auth required:** Yes

**Request body:** Any subset of the `negotiation` fields.

**Response `200`:** Updated negotiation preferences object.

---

#### `PUT /preferences/notifications`
Update notification preferences (partial update).

**Auth required:** Yes

**Request body:** Any subset of the `notifications` fields.

**Response `200`:** Updated notification preferences object.

---

### Negotiations

#### `GET /negotiations`
List all active/completed negotiations for the current user (matches not in `not_started` status).

**Auth required:** Yes

**Response `200`:**
```json
[
  {
    "id": "string — Match ID",
    "listingId": "string — Apartment ID",
    "listingTitle": "string",
    "status": "string — pending | negotiating | accepted",
    "matchScore": "float | null",
    "commuteMinutes": "integer | null",
    "createdAt": "string — ISO datetime"
  }
]
```

---

#### `POST /negotiations`
Start a negotiation for a listing. Sets the match to `in_progress` and triggers Agent 3 as a background task (if the apartment has a `host_email`).

**Auth required:** Yes

**Request body:**
```json
{
  "listingId": "string — Apartment ID"
}
```

**Response `201`:** NegotiationOut object (same shape as items in `GET /negotiations`).

**Error responses:**
- `404` — Listing not found

---

#### `GET /negotiations/{listing_id}/messages`
Retrieve the full message thread for a negotiation.

**Auth required:** Yes

**Response `200`:**
```json
[
  {
    "id": "string",
    "role": "string — agent | host | user",
    "text": "string",
    "timestamp": "string — ISO datetime"
  }
]
```

**Error responses:**
- `404` — Negotiation not found

---

#### `POST /negotiations/{listing_id}/messages`
Manually add a message to a negotiation thread.

**Auth required:** Yes

**Request body:**
```json
{
  "text": "string",
  "role": "string — user | agent | host (default: user)"
}
```

**Response `201`:** MessageOut object.

**Error responses:**
- `400` — Invalid role value
- `404` — Negotiation not found

---

#### `PUT /negotiations/{listing_id}/status`
Accept, reject, or pause a negotiation.

**Auth required:** Yes

**Request body:**
```json
{
  "status": "string — accept | reject | pause"
}
```

**Response `200`:**
```json
{
  "listingId": "string",
  "status": "string — accepted | rejected | pending"
}
```

**Error responses:**
- `400` — Invalid status value
- `404` — Negotiation not found

---

### Agent

#### `GET /agent/status`
Current agent status for the authenticated user, derived from match counts and active negotiations.

**Auth required:** Yes

**Response `200`:**
```json
{
  "isRunning": "boolean",
  "currentAction": "string — human-readable description",
  "phase": "string — search | rank | negotiate | idle",
  "matchesFound": "integer",
  "negotiationsActive": "integer",
  "toursScheduled": "integer"
}
```

---

#### `POST /agent/start`
Mark the agent as running for the current user (in-memory toggle, lost on server restart).

**Auth required:** Yes

**Response `200`:**
```json
{
  "isRunning": true,
  "message": "Agent started"
}
```

---

#### `POST /agent/stop`
Pause the agent for the current user.

**Auth required:** Yes

**Response `200`:**
```json
{
  "isRunning": false,
  "message": "Agent stopped"
}
```

---

#### `GET /agent/logs`
Paginated, filterable log feed from all three agents for the current user.

**Auth required:** Yes

**Query parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | int | 1 | Page number |
| `pageSize` | int | 50 | Items per page (1–200) |
| `phase` | string | — | Filter by `search \| rank \| negotiate` |
| `level` | string | — | Filter by `info \| success \| warning \| error` |
| `since` | string | — | ISO datetime — only return logs after this time |

**Response `200`:**
```json
{
  "items": [
    {
      "id": "string",
      "timestamp": "string — ISO datetime",
      "level": "string — info | success | warning | error",
      "message": "string",
      "phase": "string — search | rank | negotiate"
    }
  ],
  "total": "integer",
  "page": "integer",
  "pageSize": "integer"
}
```

---

### Notifications

#### `GET /notifications`
Paginated notification feed for the current user.

**Auth required:** Yes

**Query parameters:**
| Parameter | Type | Default |
|-----------|------|---------|
| `page` | int | 1 |
| `pageSize` | int | 20 (max 100) |

**Response `200`:**
```json
{
  "items": [
    {
      "id": "string",
      "type": "string — match | price_drop | negotiation",
      "title": "string — first sentence of content (max 120 chars)",
      "message": "string — full content",
      "timestamp": "string — ISO datetime",
      "read": "boolean",
      "listingId": "string | null — apartment ID if linked to a match"
    }
  ],
  "total": "integer",
  "page": "integer",
  "pageSize": "integer"
}
```

---

#### `PUT /notifications/read-all`
Mark all unread notifications as read.

**Auth required:** Yes

**Response `200`:**
```json
{
  "updated": "integer — number of notifications marked read"
}
```

---

#### `PUT /notifications/{notification_id}/read`
Mark a single notification as read.

**Auth required:** Yes

**Response `200`:**
```json
{
  "id": "string",
  "read": true
}
```

**Error responses:**
- `404` — Notification not found or does not belong to current user

---

### Tours

#### `GET /tours`
List tours inferred from Agent 3 logs (heuristic keyword matching — no dedicated Tour table yet).

**Auth required:** Yes

**Response `200`:**
```json
[
  {
    "id": "string — Agent3Log ID",
    "listingId": "string",
    "listingTitle": "string",
    "scheduledAt": "string | null — log timestamp as proxy (not actual tour date)",
    "status": "string — scheduled",
    "address": "string | null",
    "notes": "string | null — AI reasoning from agent log"
  }
]
```

---

### Health

#### `GET /health`
Liveness check. No auth required.

**Response `200`:**
```json
{
  "status": "ok"
}
```
