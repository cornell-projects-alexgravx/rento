import sys
import os  # noqa: E402 — needed for sys.path before app imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import random
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.constants import DATABASE_URL

# Import Base and all models so metadata is populated
from app.database import Base  # noqa: E402
import app.models  # noqa: F401, E402
from app.models.user import User
from app.models.preferences import (
    ObjectivePreferences,
    SubjectivePreferences,
    NegotiationPreferences,
    NotificationPreferences,
)
from app.models.apartment import NeighborInfo, Apartment
from app.models.match import Match
from app.models.notification import Notification


engine = create_async_engine(DATABASE_URL, echo=False)
session_factory = async_sessionmaker(engine, expire_on_commit=False)

# ---------------------------------------------------------------------------
# Static seed data
# ---------------------------------------------------------------------------

NEIGHBORHOODS = [
    ("SoHo", "Trendy cast-iron architecture, high-end boutiques, and a vibrant arts scene."),
    ("Williamsburg", "Hipster haven with rooftop bars, vintage shops, and stunning Manhattan views."),
    ("Bushwick", "Gritty-cool artist enclave famous for massive street murals and underground music."),
    ("Upper West Side", "Classic brownstones, proximity to Central Park, and a family-friendly vibe."),
    ("Astoria", "Diverse Queens neighborhood with excellent dining, green parks, and affordable rents."),
    ("Harlem", "Rich cultural heritage, soul-food restaurants, jazz clubs, and Renaissance architecture."),
    ("Lower East Side", "Historic immigrant neighborhood turned nightlife hub with dim-sum spots and galleries."),
    ("Park Slope", "Tree-lined streets, Prospect Park access, and a laid-back Brooklyn family atmosphere."),
    ("Midtown", "The beating heart of Manhattan: skyscrapers, corporate offices, and iconic landmarks."),
    ("Crown Heights", "Caribbean-influenced community with gorgeous brownstones and a rising food scene."),
]

USERS = [
    ("Marcus Rivera", "+1 (212) 555-0192"),
    ("Priya Patel", "+1 (718) 555-0347"),
    ("Jordan Kim", "+1 (646) 555-0581"),
    ("Aaliyah Thompson", "+1 (347) 555-0764"),
    ("Connor Walsh", "+1 (929) 555-0913"),
]

IMAGE_LABELS_POOL = [
    "bright", "modern", "open-kitchen", "hardwood-floors", "high-ceilings",
    "cozy", "minimalist", "industrial", "renovated", "natural-light",
    "spacious", "city-views", "exposed-brick", "loft-style", "luxury",
]

NOTIFICATION_TYPES = ["match", "price_drop", "negotiation"]

NOTIFICATION_MESSAGES = [
    ("match", "New match found: {apt} in {hood} is a 94% match for your preferences."),
    ("price_drop", "Price drop alert: {apt} in {hood} dropped from ${old} to ${new}/mo."),
    ("negotiation", "Your agent completed a negotiation for {apt}. New offer: ${price}/mo."),
    ("match", "3 new apartments matching your criteria appeared in {hood} today."),
    ("price_drop", "Weekend deal: {apt} in {hood} is now ${new}/mo — act fast!"),
    ("negotiation", "Counter-offer received for {apt}. Review and respond before Friday."),
    ("match", "Based on your preferences, you may love this new listing in {hood}."),
    ("price_drop", "{apt} in {hood} has been reduced by $200/mo. View details now."),
]

# Price ranges by bedroom type (min, max)
PRICE_RANGES = {
    "studio": (1800, 2800),
    "1b": (2400, 3800),
    "2b": (3200, 5000),
    "3b": (4200, 6000),
    "4plus": (5000, 6500),
}

BEDROOM_TYPES = list(PRICE_RANGES.keys())

# Approximate NYC coordinates per neighborhood (lat, lon)
NEIGHBORHOOD_COORDS = {
    "SoHo": (40.7233, -74.0030),
    "Williamsburg": (40.7081, -73.9571),
    "Bushwick": (40.6942, -73.9213),
    "Upper West Side": (40.7870, -73.9754),
    "Astoria": (40.7721, -73.9302),
    "Harlem": (40.8116, -73.9465),
    "Lower East Side": (40.7157, -73.9863),
    "Park Slope": (40.6681, -73.9800),
    "Midtown": (40.7549, -73.9840),
    "Crown Heights": (40.6694, -73.9445),
}

PRIORITY_FOCUSES = ["features", "location", "price"]
NEGOTIATION_STYLES = ["polite", "professional", "assertive", "friendly"]
COMMUTE_METHODS = ["drive", "transit", "bike"]
LAUNDRY_OPTIONS = [["in_unit"], ["on_site"], ["in_unit", "on_site"], []]
PARKING_OPTIONS = [["garage"], ["street"], ["garage", "street"], []]
NEIGHBORHOOD_VIBES = [
    ["artsy", "trendy", "walkable"],
    ["quiet", "residential", "family-friendly"],
    ["diverse", "vibrant", "nightlife"],
    ["historic", "cultural", "community-oriented"],
    ["upscale", "safe", "well-connected"],
]


def rand_id() -> str:
    return str(uuid.uuid4())


def rand_date_future(days_min: int = 15, days_max: int = 120) -> date:
    return date.today() + timedelta(days=random.randint(days_min, days_max))


def rand_subset(pool: list, min_n: int = 1, max_n: int = 4) -> list:
    k = random.randint(min_n, max_n)
    return random.sample(pool, min(k, len(pool)))


async def seed(db: AsyncSession) -> None:
    # Drop and recreate all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("Tables reset.")

    # --- Neighborhoods ---
    neighborhood_objs: list[NeighborInfo] = []
    for name, desc in NEIGHBORHOODS:
        obj = NeighborInfo(id=rand_id(), name=name, description=desc)
        db.add(obj)
        neighborhood_objs.append(obj)
    await db.commit()
    print(f"Inserted {len(neighborhood_objs)} neighborhoods.")

    # --- Users ---
    user_objs: list[User] = []
    for name, phone in USERS:
        obj = User(id=rand_id(), name=name, phone=phone, created_at=datetime.utcnow())
        db.add(obj)
        user_objs.append(obj)
    await db.commit()
    print(f"Inserted {len(user_objs)} users.")

    # --- Apartments (~100) ---
    apartment_objs: list[Apartment] = []
    apt_count = 0
    per_neighborhood = 10  # 10 * 10 neighborhoods = 100
    for neighbor in neighborhood_objs:
        lat_base, lon_base = NEIGHBORHOOD_COORDS[neighbor.name]
        for i in range(per_neighborhood):
            bedroom = random.choice(BEDROOM_TYPES)
            price_min, price_max = PRICE_RANGES[bedroom]
            # Round price to nearest 50
            price = round(random.randint(price_min, price_max) / 50) * 50
            apt_id = rand_id()
            num_images = random.randint(3, 5)
            images = [f"https://picsum.photos/seed/{apt_id[:8]}-{j}/800/600" for j in range(num_images)]
            apt = Apartment(
                id=apt_id,
                name=f"{neighbor.name} {bedroom.upper()} #{random.randint(1, 30)}{chr(random.randint(65, 70))}",
                bedroom_type=bedroom,
                latitude=round(lat_base + random.uniform(-0.01, 0.01), 6),
                longitude=round(lon_base + random.uniform(-0.01, 0.01), 6),
                price=price,
                neighbor_id=neighbor.id,
                move_in_date=rand_date_future(7, 90),
                lease_length_months=random.choice([6, 12, 18, 24]),
                laundry=random.choice(LAUNDRY_OPTIONS),
                parking=random.choice(PARKING_OPTIONS),
                pets=random.choice([True, False]),
                host_phone=f"+1 (212) 555-{random.randint(1000, 9999)}",
                host_email=f"host{apt_count + 1}@rentolistings.nyc",
                images=images,
                image_labels=rand_subset(IMAGE_LABELS_POOL, 3, 5),
                created_at=datetime.utcnow(),
            )
            db.add(apt)
            apartment_objs.append(apt)
            apt_count += 1
    await db.commit()
    print(f"Inserted {len(apartment_objs)} apartments.")

    # --- Objective Preferences (one per user) ---
    for user in user_objs:
        selected = random.sample([n.id for n in neighborhood_objs], random.randint(2, 5))
        bedroom = random.choice(BEDROOM_TYPES)
        price_min, price_max = PRICE_RANGES[bedroom]
        obj = ObjectivePreferences(
            id=rand_id(),
            user_id=user.id,
            bedroom_type=bedroom,
            selected_areas=selected,
            min_budget=price_min,
            max_budget=price_max,
            move_in_date=rand_date_future(14, 60),
            move_out_date=None,
            lease_length_months=random.choice([12, 24]),
            laundry=random.choice(LAUNDRY_OPTIONS) or ["in_unit"],
            parking=random.choice(PARKING_OPTIONS),
            pets=random.choice([True, False]),
            work_latitude=round(40.7549 + random.uniform(-0.05, 0.05), 6),
            work_longitude=round(-73.9840 + random.uniform(-0.05, 0.05), 6),
            commute_method=random.choice(COMMUTE_METHODS),
            max_commute_minutes=random.choice([20, 30, 45, 60]),
        )
        db.add(obj)
    await db.commit()
    print(f"Inserted {len(user_objs)} objective preference records.")

    # --- Subjective Preferences (one per user) ---
    for user in user_objs:
        obj = SubjectivePreferences(
            id=rand_id(),
            user_id=user.id,
            priority_focus=random.choice(PRIORITY_FOCUSES),
            image_labels=rand_subset(IMAGE_LABELS_POOL, 2, 5),
            neighborhood_labels=random.choice(NEIGHBORHOOD_VIBES),
        )
        db.add(obj)
    await db.commit()
    print(f"Inserted {len(user_objs)} subjective preference records.")

    # --- Negotiation Preferences (one per user) ---
    negotiable_pool = [
        "rent_price", "move_in_date", "lease_length", "deposit",
        "parking_fee", "pet_fee", "utilities", "application_fee",
    ]
    goals_pool = ["save_money", "stay_flexible", "live_better", "fit_lifestyle", "hassle_free"]
    for user in user_objs:
        obj = NegotiationPreferences(
            id=rand_id(),
            user_id=user.id,
            enable_automation=random.choice([True, False]),
            negotiable_items=rand_subset(negotiable_pool, 2, 4),
            goals=rand_subset(goals_pool, 1, 3),
            max_rent=random.randint(3000, 6000),
            max_deposit=random.randint(3000, 8000),
            latest_move_in_date=rand_date_future(30, 90),
            min_lease_months=random.choice([6, 12]),
            max_lease_months=random.choice([18, 24]),
            negotiation_style=random.choice(NEGOTIATION_STYLES),
        )
        db.add(obj)
    await db.commit()
    print(f"Inserted {len(user_objs)} negotiation preference records.")

    # --- Notification Preferences (one per user) ---
    notif_types_pool = ["match", "price_drop", "negotiation"]
    for user in user_objs:
        obj = NotificationPreferences(
            id=rand_id(),
            user_id=user.id,
            enable_notifications=True,
            auto_scheduling=random.choice([True, False]),
            notification_types=rand_subset(notif_types_pool, 2, 4),
            frequency=random.choice(["realtime", "daily", "weekly"]),
        )
        db.add(obj)
    await db.commit()
    print(f"Inserted {len(user_objs)} notification preference records.")

    # --- Matches (30, no duplicate user-apartment pairs) ---
    match_pairs: set[tuple[str, str]] = set()
    match_objs: list[Match] = []
    attempts = 0
    while len(match_objs) < 30 and attempts < 500:
        attempts += 1
        user = random.choice(user_objs)
        apt = random.choice(apartment_objs)
        pair = (user.id, apt.id)
        if pair in match_pairs:
            continue
        match_pairs.add(pair)
        score = round(random.uniform(0.55, 0.99), 2)
        match = Match(
            id=rand_id(),
            user_id=user.id,
            apartment_id=apt.id,
            status=random.choice(["not_started", "in_progress", "completed"]),
            commute_minutes=random.randint(10, 60),
            match_score=score,
            match_reasoning=(
                f"This apartment scores {score:.0%} based on budget fit, "
                f"location preference, and style compatibility."
            ),
            created_at=datetime.utcnow(),
        )
        db.add(match)
        match_objs.append(match)
    await db.commit()
    print(f"Inserted {len(match_objs)} matches.")

    # --- Notifications (10) ---
    apt_name_map = {a.id: a.name for a in apartment_objs}
    hood_map = {n.id: n.name for n in neighborhood_objs}
    apt_neighbor_map = {a.id: a.neighbor_id for a in apartment_objs}
    for i in range(10):
        user = random.choice(user_objs)
        apt = random.choice(apartment_objs)
        apt_name = apt_name_map[apt.id]
        hood = hood_map.get(apt_neighbor_map.get(apt.id, ""), "NYC")
        notif_type, template = random.choice(NOTIFICATION_MESSAGES)
        old_price = apt.price + random.randint(100, 400)
        new_price = apt.price
        content = template.format(
            apt=apt_name,
            hood=hood,
            old=old_price,
            new=new_price,
            price=new_price,
            date=(date.today() + timedelta(days=random.randint(3, 14))).strftime("%B %d"),
        )
        notif = Notification(
            id=rand_id(),
            user_id=user.id,
            timestamp=datetime.utcnow(),
            content=content,
            type=notif_type,
            read=random.choice([True, False]),
        )
        db.add(notif)
    await db.commit()
    print("Inserted 10 notifications.")

    print("\nSeed complete.")
    print(f"  Users:         {len(user_objs)}")
    print(f"  Neighborhoods: {len(neighborhood_objs)}")
    print(f"  Apartments:    {len(apartment_objs)}")
    print(f"  Obj. prefs:    {len(user_objs)}")
    print(f"  Subj. prefs:   {len(user_objs)}")
    print(f"  Neg. prefs:    {len(user_objs)}")
    print(f"  Notif. prefs:  {len(user_objs)}")
    print(f"  Matches:       {len(match_objs)}")
    print(f"  Notifications: 10")


async def main() -> None:
    async with session_factory() as db:
        await seed(db)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
