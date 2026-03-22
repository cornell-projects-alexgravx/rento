"""
DB Writer
=========
Async version — uses your app's AsyncSession (asyncpg) directly.

Usage
-----
    from app.parsers.db_writer import ListingWriter

    async with async_session_factory() as session:
        writer = ListingWriter(session)
        created, skipped = await writer.upsert_listings(listings)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Apartment, NeighborInfo

if TYPE_CHECKING:
    from app.parsers.streeteasy_email import ParsedListing

logger = logging.getLogger(__name__)


class ListingWriter:
    """
    Persists ParsedListing instances to the database using AsyncSession.

    Duplicate detection is on (streeteasy_id).  Falls back to (name, price)
    if streeteasy_id is not yet stored as a column — add a migration when ready.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_listings(
        self, listings: list[ParsedListing]
    ) -> tuple[int, int]:
        """Upsert a list of ParsedListings. Returns (created, skipped)."""
        created = 0
        skipped = 0

        for listing in listings:
            try:
                neighbor = await self._get_or_create_neighbor(listing)

                # Duplicate check on (name, price)
                result = await self._session.execute(
                    select(Apartment).filter_by(
                        name=listing.name,
                        price=listing.price,
                    )
                )
                existing = result.scalar_one_or_none()

                if existing:
                    logger.debug(
                        "Skipping duplicate: %s @ $%d", listing.name, listing.price
                    )
                    skipped += 1
                    continue

                # Parse move_in_date string → date object if needed
                move_in = _parse_date(listing.move_in_date)

                apt = Apartment(
                    name=listing.name,
                    bedroom_type=listing.bedroom_type,
                    price=listing.price,
                    neighbor_id=neighbor.id if neighbor else None,
                    host_contact=listing.host_contact,
                    latitude=listing.latitude,
                    longitude=listing.longitude,
                    move_in_date=move_in,
                    lease_length_months=listing.lease_length_months,
                    laundry=listing.laundry      or [],
                    parking=listing.parking      or [],
                    amenities=listing.amenities  or [],
                    pets=listing.pets            or False,
                    images=listing.images        or [],
                    image_labels=listing.image_labels or [],
                )
                self._session.add(apt)
                created += 1
                logger.info(
                    "Queued: %s (%s) $%d — %s",
                    listing.name,
                    listing.bedroom_type,
                    listing.price,
                    listing.neighborhood_name,
                )

            except Exception as exc:
                logger.error(
                    "Failed to upsert '%s': %s", listing.name, exc, exc_info=True
                )

        await self._session.commit()
        logger.info("DB commit: created=%d skipped=%d", created, skipped)
        return created, skipped

    async def _get_or_create_neighbor(
        self, listing: ParsedListing
    ) -> NeighborInfo | None:
        name = listing.neighborhood_name
        if not name:
            return None

        result = await self._session.execute(
            select(NeighborInfo).filter_by(name=name)
        )
        neighbor = result.scalar_one_or_none()
        if neighbor:
            return neighbor

        # Use Claude-generated description if available, else a stub
        description = (
            getattr(listing, "_claude_neighborhood_description", None)
            or f"{name} neighborhood in NYC. Description to be enriched by AI agent."
        )

        logger.info("Creating NeighborInfo stub: %s", name)
        neighbor = NeighborInfo(name=name, description=description)
        self._session.add(neighbor)
        await self._session.flush()  # get the generated ID before commit
        return neighbor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(value: str | None):
    """
    Convert a move_in_date string to a datetime.date.
    Accepts ISO format (2026-03-21) or returns None for anything else.
    """
    if not value:
        return None
    from datetime import date
    # Already a date object
    if isinstance(value, date):
        return value
    import re
    # ISO date: "2026-03-21"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(value))
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    # Anything else (e.g. "Available now", "now") → None;
    # Claude should have normalised it already but be defensive.
    logger.debug("Could not parse move_in_date %r as ISO date — storing None", value)
    return None