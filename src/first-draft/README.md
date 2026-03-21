# Rento Backend

NYC apartment search automation API built with FastAPI, SQLAlchemy 2.x (async), and PostgreSQL 16.

---

## Setup

### 1. Copy environment file

```bash
cp .env.example .env
```

### 2. Start services

```bash
docker-compose up --build
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### 3. Seed the database

```bash
docker-compose exec api python scripts/seed.py
```

This drops all tables, recreates them, and inserts:
- 5 users
- 10 NYC neighborhoods
- 100 apartments
- Preferences for each user (objective, subjective, negotiation, notification)
- 30 matches
- 50 votes
- 10 notifications

---

## API Reference

Replace `BASE_URL` with `http://localhost:8000`.

---

### Health

```bash
curl BASE_URL/health
```

---

### Users

**Create user**
```bash
curl -X POST BASE_URL/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Alex Rivera", "phone": "+1 (212) 555-0100"}'
```

**List users**
```bash
curl "BASE_URL/users?skip=0&limit=20"
```

**Get user**
```bash
curl BASE_URL/users/{user_id}
```

**Update user**
```bash
curl -X PATCH BASE_URL/users/{user_id} \
  -H "Content-Type: application/json" \
  -d '{"phone": "+1 (646) 555-0200"}'
```

**Delete user**
```bash
curl -X DELETE BASE_URL/users/{user_id}
```

---

### Objective Preferences

**Set objective preferences**
```bash
curl -X POST BASE_URL/users/{user_id}/objective-preferences \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "{user_id}",
    "bedroom_type": "1b",
    "selected_areas": ["{neighborhood_id}"],
    "min_budget": 2400,
    "max_budget": 3800,
    "move_in_date": "2026-05-01",
    "laundry": ["in_unit"],
    "parking": [],
    "amenities": ["gym", "doorman"],
    "pets": false,
    "commute_method": "transit",
    "max_commute_minutes": 30
  }'
```

**List objective preferences for user**
```bash
curl BASE_URL/users/{user_id}/objective-preferences
```

**Get specific objective preference**
```bash
curl BASE_URL/users/{user_id}/objective-preferences/{pref_id}
```

**Update objective preferences**
```bash
curl -X PATCH BASE_URL/users/{user_id}/objective-preferences/{pref_id} \
  -H "Content-Type: application/json" \
  -d '{"max_budget": 4200, "pets": true}'
```

**Delete objective preferences**
```bash
curl -X DELETE BASE_URL/users/{user_id}/objective-preferences/{pref_id}
```

---

### Subjective Preferences

**Set subjective preferences**
```bash
curl -X POST BASE_URL/users/{user_id}/subjective-preferences \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "{user_id}",
    "priority_focus": "location",
    "image_labels": ["bright", "modern", "minimalist"],
    "neighborhood_labels": ["walkable", "vibrant"]
  }'
```

**List / Get / Update / Delete** follow the same pattern as objective preferences using `/users/{user_id}/subjective-preferences/{pref_id}`.

---

### Negotiation Preferences

**Set negotiation preferences**
```bash
curl -X POST BASE_URL/users/{user_id}/negotiation-preferences \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "{user_id}",
    "enable_automation": true,
    "negotiable_items": ["rent_price", "deposit", "lease_length"],
    "goals": ["save_money", "stay_flexible"],
    "max_rent": 3500,
    "max_deposit": 7000,
    "latest_move_in_date": "2026-06-01",
    "min_lease_months": 12,
    "max_lease_months": 24,
    "negotiation_style": "professional"
  }'
```

**List / Get / Update / Delete** use `/users/{user_id}/negotiation-preferences/{pref_id}`.

---

### Notification Preferences

**Set notification preferences**
```bash
curl -X POST BASE_URL/users/{user_id}/notification-preferences \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "{user_id}",
    "enable_notifications": true,
    "auto_scheduling": false,
    "notification_types": ["match", "price_drop"],
    "frequency": "daily"
  }'
```

**List / Get / Update / Delete** use `/users/{user_id}/notification-preferences/{pref_id}`.

---

### Neighborhoods

**List neighborhoods**
```bash
curl "BASE_URL/neighborhoods?skip=0&limit=20"
```

**Get neighborhood**
```bash
curl BASE_URL/neighborhoods/{neighborhood_id}
```

**Create neighborhood**
```bash
curl -X POST BASE_URL/neighborhoods \
  -H "Content-Type: application/json" \
  -d '{"name": "Greenpoint", "description": "Waterfront Polish enclave with indie coffee shops and art galleries."}'
```

**Update neighborhood**
```bash
curl -X PATCH BASE_URL/neighborhoods/{neighborhood_id} \
  -H "Content-Type: application/json" \
  -d '{"description": "Updated description."}'
```

**Delete neighborhood**
```bash
curl -X DELETE BASE_URL/neighborhoods/{neighborhood_id}
```

---

### Apartments

**List apartments with filters**
```bash
curl "BASE_URL/apartments?bedroom_type=1b&min_price=2000&max_price=4000&pets=true&skip=0&limit=20"
```

**Get apartment**
```bash
curl BASE_URL/apartments/{apartment_id}
```

**Create apartment**
```bash
curl -X POST BASE_URL/apartments \
  -H "Content-Type: application/json" \
  -d '{
    "name": "SoHo Loft #4A",
    "bedroom_type": "1b",
    "latitude": 40.7233,
    "longitude": -74.0030,
    "price": 3200,
    "neighbor_id": "{neighborhood_id}",
    "move_in_date": "2026-05-15",
    "lease_length_months": 12,
    "laundry": ["in_unit"],
    "parking": [],
    "amenities": ["gym", "rooftop", "doorman"],
    "pets": false,
    "host_contact": "host@example.com",
    "images": ["https://picsum.photos/seed/abc/800/600"],
    "image_labels": ["bright", "modern", "high-ceilings"]
  }'
```

**Update apartment**
```bash
curl -X PATCH BASE_URL/apartments/{apartment_id} \
  -H "Content-Type: application/json" \
  -d '{"price": 3000, "pets": true}'
```

**Delete apartment**
```bash
curl -X DELETE BASE_URL/apartments/{apartment_id}
```

---

### Matches

**Create a match**
```bash
curl -X POST BASE_URL/matches \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "{user_id}",
    "apartment_id": "{apartment_id}",
    "status": "not_started",
    "commute_minutes": 25,
    "match_score": 0.92,
    "match_reasoning": "Strong budget and location alignment with 4 matching amenities."
  }'
```

**List all matches**
```bash
curl "BASE_URL/matches?skip=0&limit=20"
```

**Get match**
```bash
curl BASE_URL/matches/{match_id}
```

**Get user matches**
```bash
curl "BASE_URL/users/{user_id}/matches?skip=0&limit=20"
```

**Update match**
```bash
curl -X PATCH BASE_URL/matches/{match_id} \
  -H "Content-Type: application/json" \
  -d '{"status": "in_progress"}'
```

**Delete match**
```bash
curl -X DELETE BASE_URL/matches/{match_id}
```

---

### Votes

**Cast a vote**
```bash
curl -X POST BASE_URL/votes \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "{user_id}",
    "apartment_id": "{apartment_id}",
    "vote": "love"
  }'
```

**List all votes**
```bash
curl "BASE_URL/votes?skip=0&limit=50"
```

**Get vote**
```bash
curl BASE_URL/votes/{vote_id}
```

**Get user votes**
```bash
curl "BASE_URL/users/{user_id}/votes"
```

**Update vote**
```bash
curl -X PATCH BASE_URL/votes/{vote_id} \
  -H "Content-Type: application/json" \
  -d '{"vote": "dislike"}'
```

**Delete vote**
```bash
curl -X DELETE BASE_URL/votes/{vote_id}
```

---

### Messages

**Create message**
```bash
curl -X POST BASE_URL/messages \
  -H "Content-Type: application/json" \
  -d '{
    "match_id": "{match_id}",
    "type": "agent",
    "text": "Hi, I am reaching out on behalf of a tenant interested in your listing."
  }'
```

**List messages**
```bash
curl "BASE_URL/messages?skip=0&limit=50"
```

**Get message**
```bash
curl BASE_URL/messages/{message_id}
```

**Update message**
```bash
curl -X PATCH BASE_URL/messages/{message_id} \
  -H "Content-Type: application/json" \
  -d '{"text": "Updated message text."}'
```

**Delete message**
```bash
curl -X DELETE BASE_URL/messages/{message_id}
```

---

### Notifications

**Get user notifications**
```bash
curl "BASE_URL/users/{user_id}/notifications?skip=0&limit=20"
```

**List all notifications**
```bash
curl "BASE_URL/notifications?skip=0&limit=50"
```

**Get notification**
```bash
curl BASE_URL/notifications/{notification_id}
```

**Create notification**
```bash
curl -X POST BASE_URL/notifications \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "{user_id}",
    "content": "New match found in Williamsburg at 92% compatibility.",
    "type": "match"
  }'
```

**Mark notification as read**
```bash
curl -X PATCH BASE_URL/notifications/{notification_id}/read
```

**Update notification**
```bash
curl -X PATCH BASE_URL/notifications/{notification_id} \
  -H "Content-Type: application/json" \
  -d '{"read": true}'
```

**Delete notification**
```bash
curl -X DELETE BASE_URL/notifications/{notification_id}
```

---

### Agent Logs

**Agent 1 (apartment scraping/discovery)**
```bash
# Create
curl -X POST BASE_URL/agent-logs/agent1 \
  -H "Content-Type: application/json" \
  -d '{"apartment_id": "{apartment_id}", "source": "streeteasy.com", "content": "Scraped listing data.", "result": "success"}'

# List
curl "BASE_URL/agent-logs/agent1?skip=0&limit=20"

# Get
curl BASE_URL/agent-logs/agent1/{log_id}

# Update
curl -X PATCH BASE_URL/agent-logs/agent1/{log_id} \
  -H "Content-Type: application/json" \
  -d '{"result": "processed"}'

# Delete
curl -X DELETE BASE_URL/agent-logs/agent1/{log_id}
```

**Agent 2 (image analysis)**
```bash
curl -X POST BASE_URL/agent-logs/agent2 \
  -H "Content-Type: application/json" \
  -d '{"apartment_id": "{apartment_id}", "content": "Analyzed 4 images.", "result": "bright,modern,hardwood-floors"}'
```

**Agent 3 (matching/negotiation)**
```bash
curl -X POST BASE_URL/agent-logs/agent3 \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "{user_id}",
    "apartment_id": "{apartment_id}",
    "content": "Running match scoring for user preferences.",
    "result": "score=0.94"
  }'
```

---

## Enum Reference

| Field | Valid values |
|---|---|
| `bedroom_type` | `studio`, `1b`, `2b`, `3b`, `4plus` |
| `laundry[]` | `in_unit`, `on_site` |
| `parking[]` | `garage`, `street` |
| `commute_method` | `drive`, `transit`, `bike` |
| `priority_focus` | `features`, `location`, `price` |
| `negotiation_style` | `polite`, `professional`, `assertive`, `friendly` |
| `negotiable_items[]` | `rent_price`, `move_in_date`, `lease_length`, `deposit`, `parking_fee`, `pet_fee`, `utilities`, `furnishing`, `application_fee`, `promotions` |
| `goals[]` | `save_money`, `stay_flexible`, `live_better`, `fit_lifestyle`, `hassle_free` |
| `notification type` | `match`, `price_drop`, `negotiation`, `tour` |
| `frequency` | `realtime`, `daily`, `weekly` |
| `match status` | `not_started`, `in_progress`, `completed` |
| `vote` | `like`, `dislike`, `love` |
| `message type` | `agent`, `host` |
