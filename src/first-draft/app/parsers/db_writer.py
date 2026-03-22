"""
DB Writer
=========
Converts ParsedListing dataclasses into SQLAlchemy Apartment +
NeighborInfo rows and upserts them into the database.

This module is intentionally side-effect-free with respect to business
logic: it does NOT override latitude/longitude, amenities, etc.  Those
fields are populated later by the AI enrichment agents.

Usage
-----
    from db_writer import ListingWriter

    writer = ListingWriter(db_session)
    created, skipped = writer.upsert_listings(parsed_listings)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from streeteasy_email import ParsedListing

# Import your app models — adjust the import path to match your project layout.
# from app.models import Apartment, NeighborInfo

logger = logging.getLogger(__name__)


class ListingWriter:
    """
    Persists ParsedListing instances to the database.

    Duplicate detection: we treat (name + price) as a soft unique key so
    that re-running the pipeline on the same email is idempotent.
    A proper unique constraint on streeteasy_id would be even better —
    add one to the Apartment table migration when ready.

    Parameters
    ----------
    session:
        An active SQLAlchemy Session.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    # ---------------------------------------------------------------------------

    def upsert_listings(
        self, listings: list["ParsedListing"]
    ) -> tuple[int, int]:
        """
        Upsert a list of ParsedListing objects.

        Returns
        -------
        (created, skipped) counts.
        """
        # Import here to allow the module to be imported without the app context.
        from ..models import Apartment, NeighborInfo  # noqa: PLC0415

        created = 0
        skipped = 0

        for listing in listings:
            try:
                # 1. Resolve or create the NeighborInfo record.
                neighbor = self._get_or_create_neighbor(
                    listing.neighborhood_name, NeighborInfo
                )

                # 2. Check for an existing Apartment with the same address & price.
                existing = (
                    self._session.query(Apartment)
                    .filter_by(name=listing.name, price=listing.price)
                    .first()
                )
                if existing:
                    logger.debug(
                        "Skipping duplicate listing: %s @ $%d",
                        listing.name,
                        listing.price,
                    )
                    skipped += 1
                    continue

                # 3. Create the Apartment record.
                apt = Apartment(
                    name=listing.name,
                    bedroom_type=listing.bedroom_type,
                    price=listing.price,
                    neighbor_id=neighbor.id if neighbor else None,
                    host_contact=listing.host_contact,
                    # Fields intentionally left for the enrichment agents:
                    latitude=listing.latitude,
                    longitude=listing.longitude,
                    move_in_date=listing.move_in_date,
                    lease_length_months=listing.lease_length_months,
                    laundry=listing.laundry,
                    parking=listing.parking,
                    amenities=listing.amenities,
                    pets=listing.pets,
                    images=listing.images,
                    image_labels=listing.image_labels,
                )
                self._session.add(apt)
                created += 1
                logger.info(
                    "Queued new listing: %s (%s) @ $%d in %s",
                    listing.name,
                    listing.bedroom_type,
                    listing.price,
                    listing.neighborhood_name,
                )

            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Failed to upsert listing '%s': %s", listing.name, exc, exc_info=True
                )

        self._session.commit()
        logger.info("DB commit: created=%d, skipped=%d", created, skipped)
        return created, skipped

    # ---------------------------------------------------------------------------

    def _get_or_create_neighbor(
        self, name: str, NeighborInfo  # type: ignore[valid-type]
    ):
        """Return an existing NeighborInfo row or create a new stub."""
        if not name:
            return None

        neighbor = (
            self._session.query(NeighborInfo).filter_by(name=name).first()
        )
        if neighbor:
            return neighbor

        logger.info("Creating new NeighborInfo stub for: %s", name)
        neighbor = NeighborInfo(
            name=name,
            description=f"Automatically created from StreetEasy email alert. "
                        f"Description to be enriched by AI agent.",
        )
        self._session.add(neighbor)
        self._session.flush()  # get the auto-generated ID before commit
        return neighbor