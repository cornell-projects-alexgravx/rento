# Database Design

## Overview

PostgreSQL 16, accessed via SQLAlchemy async ORM with the `asyncpg` driver. Connection string pattern:

```
postgresql+asyncpg://<user>:<password>@<host>:5432/<dbname>
```

Tables are created at application startup via `Base.metadata.create_all` (no Alembic migrations). All primary keys are string UUIDs generated in Python.

## Entity Relationship Summary

A `User` has one set of preferences (spread across four tables), many `Match` rows (one per apartment they qualified for), and many `Notification` rows. An `Apartment` belongs to a `NeighborInfo` neighborhood and has many `Match` rows. A `Match` links a user to an apartment and tracks negotiation status, AI score, and commute time. `Message` rows record the negotiation email thread per match. The three agent log tables (`Agent1Log`, `Agent2Log`, `Agent3Log`) record the output of each AI agent run.

---

## Tables

### `users`
Registered users of the platform.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | VARCHAR | PK, default UUID | User identifier |
| `name` | VARCHAR | NOT NULL | Display name |
| `phone` | VARCHAR | nullable | Phone number (optional) |
| `email` | VARCHAR | nullable, UNIQUE, INDEX | Login email |
| `hashed_password` | VARCHAR | nullable | bcrypt hash |
| `created_at` | TIMESTAMP WITH TZ | default `utcnow` | Account creation time |

**Relationships:**
- `objective_preferences` → `ObjectivePreferences[]` (cascade delete)
- `subjective_preferences` → `SubjectivePreferences[]` (cascade delete)
- `negotiation_preferences` → `NegotiationPreferences[]` (cascade delete)
- `notification_preferences` → `NotificationPreferences[]` (cascade delete)
- `matches` → `Match[]` (cascade delete)
- `notifications` → `Notification[]` (cascade delete)
- `agent2_logs` → `Agent2Log[]` (cascade delete)
- `agent3_logs` → `Agent3Log[]` (cascade delete)

---

### `neighbor_info`
NYC neighborhood descriptors used for semantic matching.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | VARCHAR | PK, default UUID | Neighborhood identifier |
| `name` | VARCHAR | NOT NULL | Neighborhood name (e.g. `"Brooklyn Heights"`) |
| `description` | VARCHAR | NOT NULL | Text description used by Agent 2 |

**Relationships:**
- `apartments` → `Apartment[]` (cascade delete on neighborhood delete)

---

### `apartments`
Apartment listings ingested from Craigslist and StreetEasy.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | VARCHAR | PK, default UUID | Apartment identifier |
| `streeteasy_id` | VARCHAR | nullable, UNIQUE | StreetEasy listing ID (dedup key) |
| `craigslist_id` | VARCHAR | nullable, UNIQUE | Craigslist listing ID (dedup key) |
| `name` | VARCHAR | NOT NULL | Listing title/address |
| `bedroom_type` | VARCHAR | NOT NULL | Bedroom type (see enums) |
| `latitude` | FLOAT | nullable | Geolocation latitude |
| `longitude` | FLOAT | nullable | Geolocation longitude |
| `price` | INTEGER | NOT NULL | Monthly rent in USD |
| `neighbor_id` | VARCHAR | FK → `neighbor_info.id` ON DELETE SET NULL, nullable | Neighborhood reference |
| `move_in_date` | DATE | nullable | Earliest available move-in date |
| `lease_length_months` | INTEGER | nullable | Lease term in months |
| `laundry` | VARCHAR[] | default `[]` | Laundry options available |
| `parking` | VARCHAR[] | default `[]` | Parking options available |
| `pets` | BOOLEAN | default `false` | Pets allowed |
| `host_phone` | VARCHAR | nullable | Landlord phone |
| `host_email` | VARCHAR | nullable | Landlord email (required for Agent 3) |
| `amenities` | VARCHAR[] | default `[]` | General amenity list |
| `images` | VARCHAR[] | default `[]` | Image URLs |
| `image_labels` | VARCHAR[] | default `[]` | Style labels from Agent 1 (e.g. `["bright", "minimalist"]`) |
| `created_at` | TIMESTAMP WITH TZ | default `utcnow` | Ingestion timestamp |

**Relationships:**
- `neighborhood` → `NeighborInfo` (many-to-one)
- `matches` → `Match[]` (cascade delete)
- `agent1_logs` → `Agent1Log[]` (cascade delete)
- `agent3_logs` → `Agent3Log[]` (SET NULL on apartment delete)

---

### `objective_preferences`
Hard filter criteria set during onboarding. Used by the matching filter to create `Match` rows.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | VARCHAR | PK, default UUID | — |
| `user_id` | VARCHAR | FK → `users.id` CASCADE, NOT NULL, INDEX | Owner |
| `bedroom_type` | VARCHAR | NOT NULL | Required bedroom type |
| `selected_areas` | VARCHAR[] | default `[]` | Preferred neighborhoods |
| `min_budget` | INTEGER | NOT NULL | Minimum monthly rent |
| `max_budget` | INTEGER | NOT NULL | Maximum monthly rent |
| `move_in_date` | DATE | NOT NULL | Earliest acceptable move-in date |
| `move_out_date` | DATE | nullable | Latest move-out date (if applicable) |
| `lease_length_months` | INTEGER | nullable | Preferred lease length |
| `laundry` | VARCHAR[] | default `[]` | Required laundry options |
| `parking` | VARCHAR[] | default `[]` | Required parking options |
| `pets` | BOOLEAN | default `false` | Must allow pets |
| `work_latitude` | FLOAT | nullable | Work location for commute calculation |
| `work_longitude` | FLOAT | nullable | Work location for commute calculation |
| `commute_method` | VARCHAR | nullable | `drive \| transit \| bike` |
| `max_commute_minutes` | INTEGER | nullable | Maximum acceptable commute time |

---

### `subjective_preferences`
Style and neighborhood preferences used by Agent 2 for semantic scoring.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | VARCHAR | PK, default UUID | — |
| `user_id` | VARCHAR | FK → `users.id` CASCADE, NOT NULL, INDEX | Owner |
| `priority_focus` | VARCHAR | nullable | `features \| location \| price` |
| `image_labels` | VARCHAR[] | default `[]` | Preferred apartment style labels |
| `neighborhood_labels` | VARCHAR[] | default `[]` | Preferred neighborhood vibes |

---

### `negotiation_preferences`
Controls how Agent 3 negotiates on behalf of the user.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | VARCHAR | PK, default UUID | — |
| `user_id` | VARCHAR | FK → `users.id` CASCADE, NOT NULL | Owner |
| `enable_automation` | BOOLEAN | default `false` | Whether Agent 3 is allowed to run |
| `negotiable_items` | VARCHAR[] | default `[]` | Items open to negotiation (e.g. `rent_price`, `deposit`) |
| `goals` | VARCHAR[] | default `[]` | Negotiation goals (e.g. `save_money`, `hassle_free`) |
| `max_rent` | INTEGER | nullable | Maximum acceptable rent after negotiation |
| `max_deposit` | INTEGER | nullable | Maximum acceptable deposit |
| `latest_move_in_date` | DATE | nullable | Latest acceptable move-in date |
| `min_lease_months` | INTEGER | nullable | Minimum lease term |
| `max_lease_months` | INTEGER | nullable | Maximum lease term |
| `negotiation_style` | VARCHAR | nullable | `polite \| professional \| assertive \| friendly` |

---

### `notification_preferences`
Controls when and how the user receives in-app notifications.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | VARCHAR | PK, default UUID | — |
| `user_id` | VARCHAR | FK → `users.id` CASCADE, NOT NULL | Owner |
| `enable_notifications` | BOOLEAN | default `true` | Master notification toggle |
| `auto_scheduling` | BOOLEAN | default `false` | Auto-schedule tours when confirmed |
| `notification_types` | VARCHAR[] | default `[]` | Types to receive: `match`, `price_drop`, `negotiation` |
| `frequency` | VARCHAR | default `"realtime"` | `realtime \| daily \| weekly` |

---

### `matches`
Join table between users and apartments, also stores AI scoring and negotiation state.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | VARCHAR | PK, default UUID | — |
| `user_id` | VARCHAR | FK → `users.id` CASCADE, NOT NULL, INDEX | User who matched |
| `apartment_id` | VARCHAR | FK → `apartments.id` CASCADE, NOT NULL | Matched apartment |
| `status` | VARCHAR | default `"not_started"` | `not_started \| in_progress \| completed` |
| `commute_minutes` | INTEGER | nullable | Calculated commute from work location |
| `match_score` | FLOAT | nullable | AI score normalized to 0.0–1.0 |
| `match_reasoning` | VARCHAR | nullable | One-sentence Claude explanation |
| `created_at` | TIMESTAMP WITH TZ | default `utcnow` | When this match was created |

**Constraints:**
- `UNIQUE (user_id, apartment_id)` — a user can only match an apartment once

**Relationships:**
- `user` → `User`
- `apartment` → `Apartment`
- `messages` → `Message[]` (cascade delete)

---

### `messages`
Email thread messages for a negotiation (agent outbound + host inbound).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | VARCHAR | PK, default UUID | — |
| `match_id` | VARCHAR | FK → `matches.id` ON DELETE SET NULL, nullable | Associated negotiation |
| `type` | VARCHAR | NOT NULL | `agent \| host \| user` |
| `timestamp` | TIMESTAMP WITH TZ | default `utcnow` | Message time |
| `text` | TEXT | NOT NULL | Message body |

**Relationships:**
- `match` → `Match`
- `agent3_logs` → `Agent3Log[]` (SET NULL on message delete)

---

### `notifications`
In-app notifications generated by Agent 3 on negotiation outcome.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | VARCHAR | PK, default UUID | — |
| `user_id` | VARCHAR | FK → `users.id` CASCADE, NOT NULL | Recipient |
| `timestamp` | TIMESTAMP WITH TZ | default `utcnow` | Creation time |
| `content` | TEXT | NOT NULL | Full notification text |
| `type` | VARCHAR | NOT NULL | `match \| price_drop \| negotiation` |
| `read` | BOOLEAN | default `false` | Whether the user has read it |
| `match_id` | VARCHAR | FK → `matches.id` ON DELETE SET NULL, nullable | Linked negotiation (if any) |

---

### `agent1_logs`
Audit trail of Agent 1 (image analysis) runs, one row per apartment processed.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | VARCHAR | PK, default UUID | — |
| `apartment_id` | VARCHAR | FK → `apartments.id` CASCADE, NOT NULL | Analyzed apartment |
| `source` | VARCHAR | nullable | Always `"agent1_image"` |
| `timestamp` | TIMESTAMP WITH TZ | default `utcnow` | Run time |
| `result` | TEXT | nullable | JSON: `{status, labels_count, labels, description}` or `{status, error}` |

---

### `agent2_logs`
Audit trail of Agent 2 (semantic ranking) runs, one row per user ranking pass.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | VARCHAR | PK, default UUID | — |
| `user_id` | VARCHAR | FK → `users.id` CASCADE, NOT NULL | User whose matches were scored |
| `timestamp` | TIMESTAMP WITH TZ | default `utcnow` | Run time |
| `result` | TEXT | nullable | JSON: `{status, ranked_count, reasoning_description}` or `{status, error}` |

---

### `agent3_logs`
Audit trail of Agent 3 (negotiation) runs, one row per email sent or reply received.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | VARCHAR | PK, default UUID | — |
| `user_id` | VARCHAR | FK → `users.id` CASCADE, NOT NULL | User running the negotiation |
| `apartment_id` | VARCHAR | FK → `apartments.id` ON DELETE SET NULL, nullable | Target apartment |
| `message_id` | VARCHAR | FK → `messages.id` ON DELETE SET NULL, nullable | Associated message row |
| `timestamp` | TIMESTAMP WITH TZ | default `utcnow` | Event time |
| `result` | TEXT | nullable | JSON: `{status, round, contact_channel, contact_address, ai_reasoning, message}` |

---

## Enums

These are Python `str` enums used in application code. They are stored as plain VARCHAR in PostgreSQL (no `CREATE TYPE` enum constraint at the DB level).

| Enum | Values |
|------|--------|
| `BedroomType` | `studio`, `1b`, `2b`, `3b`, `4plus` |
| `LaundryType` | `in_unit`, `on_site` |
| `ParkingType` | `garage`, `street` |
| `CommuteMethod` | `drive`, `transit`, `bike` |
| `PriorityFocus` | `features`, `location`, `price` |
| `NegotiationStyle` | `polite`, `professional`, `assertive`, `friendly` |
| `NegotiableItem` | `rent_price`, `move_in_date`, `lease_length`, `deposit`, `parking_fee`, `pet_fee`, `utilities`, `furnishing`, `application_fee`, `promotions` |
| `NegotiationGoal` | `save_money`, `stay_flexible`, `live_better`, `fit_lifestyle`, `hassle_free` |
| `NotificationType` | `match`, `price_drop`, `negotiation` |
| `NotificationFrequency` | `realtime`, `daily`, `weekly` |
| `MatchStatus` | `not_started`, `in_progress`, `completed` |
| `MessageType` | `agent`, `host` |
