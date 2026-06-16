"""Insert the demo apartment used for negotiate demos.

Apartment ID is fixed as 'lst-demo-001' so the frontend mock listing
(same ID) works when the backend is running.

Run once:
    cd backend
    python scripts/add_demo_apt.py

To send real emails to zzzjk445@gmail.com, configure .env:
    SMTP_HOST=smtp.gmail.com
    SMTP_PORT=587
    SMTP_USE_TLS=true
    SMTP_FROM=your-sending-address@gmail.com
    SMTP_USERNAME=your-sending-address@gmail.com
    SMTP_PASSWORD=your-gmail-app-password
"""
import asyncio
import sys
import os
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.constants import DATABASE_URL
from app.database import Base
import app.models  # noqa: F401
from app.models.apartment import Apartment

DEMO_ID = "lst-demo-001"

engine = create_async_engine(DATABASE_URL, echo=False)
session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def add_demo() -> None:
    async with session_factory() as session:
        existing = await session.get(Apartment, DEMO_ID)
        if existing:
            # Update host_email in case it changed
            existing.host_email = "zzzjk445@gmail.com"
            await session.commit()
            print(f"Demo apartment already exists — host_email updated to zzzjk445@gmail.com")
            return

        apt = Apartment(
            id=DEMO_ID,
            name="Modern 1BR in Williamsburg",
            bedroom_type="1b",
            latitude=40.7081,
            longitude=-73.9571,
            price=2500,
            neighbor_id=None,
            move_in_date=date.today() + timedelta(days=30),
            lease_length_months=12,
            laundry=["on_site"],
            parking=[],
            pets=False,
            host_phone="+1 (718) 555-0001",
            host_email="zzzjk445@gmail.com",
            images=[
                "https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?w=800",
                "https://images.unsplash.com/photo-1560448204-e02f11c3d0e2?w=800",
            ],
            image_labels=["bright", "modern", "hardwood-floors"],
            created_at=datetime.utcnow(),
        )
        session.add(apt)
        await session.commit()
        print(f"Inserted demo apartment id={DEMO_ID} with host_email=zzzjk445@gmail.com")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(add_demo())
