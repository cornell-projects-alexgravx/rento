"""GET /api/v1/listings, GET /api/v1/listings/:id, POST /api/v1/listings/:id/react

A "listing" is an Apartment enriched with its Match data for the current user.
"""
from __future__ import annotations

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.apartment import Apartment
from app.models.match import Match
from app.models.user import User
from app.routers.v1.deps import get_current_user

router = APIRouter(prefix="/listings", tags=["v1-listings"])


# ---------------------------------------------------------------------------
# Out schemas
# ---------------------------------------------------------------------------


class ListingOut(BaseModel):
    id: str
    title: str
    address: str
    neighborhood: str | None
    price: int
    bedrooms: str
    pets: bool
    parking: list[str]
    laundry: list[str]
    images: list[str]
    imageLabels: list[str]
    lat: float | None
    lng: float | None
    availableFrom: str | None
    leaseLength: int | None
    matchScore: float | None
    matchReasoning: str | None
    negotiationStatus: str | None
    commuteMinutes: int | None
    matchId: str | None
    matchType: str  # "perfect" | "flex"
    status: str  # "available" | "pending" | "unavailable"
    hostEmail: str | None
    hostPhone: str | None


class PaginatedListings(BaseModel):
    items: list[ListingOut]
    total: int
    page: int
    pageSize: int


# ---------------------------------------------------------------------------
# Mapping helper: Match.status → NegotiationStatus expected by frontend
# ---------------------------------------------------------------------------

_STATUS_MAP = {
    "not_started": "pending",
    "in_progress": "negotiating",
    "completed": "accepted",
}


def _to_negotiation_status(match_status: str) -> str:
    return _STATUS_MAP.get(match_status, match_status)


# ---------------------------------------------------------------------------
# Converter
# ---------------------------------------------------------------------------


def _to_match_type(score: float | None) -> str:
    """Derive matchType from the match score: >= 0.85 is 'perfect', else 'flex'."""
    if score is None:
        return "flex"
    # Scores are stored as 0-1 float OR 0-100. Normalise to 0-1 for the threshold.
    normalised = score / 100.0 if score > 1 else score
    return "perfect" if normalised >= 0.85 else "flex"


def _build_listing(apt: Apartment, match: Match | None) -> ListingOut:
    score = match.match_score if match else None
    return ListingOut(
        id=apt.id,
        title=apt.name,
        address=apt.name,
        neighborhood=apt.neighborhood.name if apt.neighborhood else None,
        price=apt.price,
        bedrooms=apt.bedroom_type,
        pets=apt.pets,
        parking=apt.parking or [],
        laundry=apt.laundry or [],
        images=apt.images or [],
        imageLabels=apt.image_labels or [],
        lat=apt.latitude,
        lng=apt.longitude,
        availableFrom=apt.move_in_date.isoformat() if apt.move_in_date else None,
        leaseLength=apt.lease_length_months,
        matchScore=score,
        matchReasoning=match.match_reasoning if match else None,
        negotiationStatus=_to_negotiation_status(match.status) if match else None,
        commuteMinutes=match.commute_minutes if match else None,
        matchId=match.id if match else None,
        matchType=_to_match_type(score),
        status="available",  # Apartment model has no status column; default to available
        hostEmail=apt.host_email,
        hostPhone=apt.host_phone,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedListings)
async def list_listings(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    # Filtering
    negotiationStatus: Optional[str] = Query(default=None),
    matchType: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    minPrice: Optional[int] = Query(default=None),
    maxPrice: Optional[int] = Query(default=None),
    minScore: Optional[float] = Query(default=None),
    # Sorting
    sortBy: Optional[str] = Query(default=None),  # "price" | "matchScore" | "commuteMinutes"
    sortOrder: Optional[str] = Query(default="desc"),  # "asc" | "desc"
) -> PaginatedListings:
    uid = current_user.id

    # Build apartment query with optional price filters
    apt_query = select(Apartment).options(selectinload(Apartment.neighborhood))
    if minPrice is not None:
        apt_query = apt_query.where(Apartment.price >= minPrice)
    if maxPrice is not None:
        apt_query = apt_query.where(Apartment.price <= maxPrice)

    # Apply price sort at DB level if requested
    if sortBy == "price":
        if sortOrder == "asc":
            apt_query = apt_query.order_by(Apartment.price.asc())
        else:
            apt_query = apt_query.order_by(Apartment.price.desc())

    apts_result = await db.execute(apt_query)
    all_apts = apts_result.scalars().all()

    # Fetch this user's matches for all apartments in one query
    all_apt_ids = [a.id for a in all_apts]
    matches_result = await db.execute(
        select(Match).where(Match.user_id == uid, Match.apartment_id.in_(all_apt_ids))
    )
    match_by_apt: dict[str, Match] = {m.apartment_id: m for m in matches_result.scalars().all()}

    # Build listing objects
    items_all = [_build_listing(apt, match_by_apt.get(apt.id)) for apt in all_apts]

    # Apply post-fetch filters
    if negotiationStatus:
        items_all = [i for i in items_all if i.negotiationStatus == negotiationStatus]
    if matchType:
        items_all = [i for i in items_all if i.matchType == matchType]
    if status:
        items_all = [i for i in items_all if i.status == status]
    if minScore is not None:
        items_all = [i for i in items_all if (i.matchScore or 0) >= minScore]

    # Apply sorting for fields not handled at DB level
    if sortBy == "matchScore":
        reverse = sortOrder != "asc"
        items_all.sort(key=lambda x: x.matchScore or 0, reverse=reverse)
    elif sortBy == "commuteMinutes":
        reverse = sortOrder == "desc"
        items_all.sort(key=lambda x: x.commuteMinutes or 9999, reverse=reverse)

    total = len(items_all)
    offset = (page - 1) * pageSize
    paged = items_all[offset : offset + pageSize]

    return PaginatedListings(items=paged, total=total, page=page, pageSize=pageSize)


@router.get("/{listing_id}", response_model=ListingOut)
async def get_listing(
    listing_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> ListingOut:
    apt_result = await db.execute(
        select(Apartment)
        .options(selectinload(Apartment.neighborhood))
        .where(Apartment.id == listing_id)
    )
    apt = apt_result.scalar_one_or_none()
    if not apt:
        raise HTTPException(status_code=404, detail="Listing not found")

    match = (
        await db.execute(
            select(Match).where(
                Match.user_id == current_user.id, Match.apartment_id == listing_id
            ).limit(1)
        )
    ).scalar_one_or_none()

    return _build_listing(apt, match)


# ---------------------------------------------------------------------------
# React (like / dislike → creates or updates a Match row)
# ---------------------------------------------------------------------------


class ReactRequest(BaseModel):
    action: str  # "like" | "dislike"


class ReactResponse(BaseModel):
    matchId: str | None
    action: str


@router.post("/{listing_id}/react", response_model=ReactResponse)
async def react_to_listing(
    listing_id: str,
    body: ReactRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
) -> ReactResponse:
    apt = await db.get(Apartment, listing_id)
    if not apt:
        raise HTTPException(status_code=404, detail="Listing not found")

    match = (
        await db.execute(
            select(Match).where(
                Match.user_id == current_user.id, Match.apartment_id == listing_id
            ).limit(1)
        )
    ).scalar_one_or_none()

    if body.action == "like":
        if match is None:
            match = Match(
                id=str(uuid.uuid4()),
                user_id=current_user.id,
                apartment_id=listing_id,
                status="not_started",
            )
            db.add(match)
            await db.commit()
            await db.refresh(match)
        return ReactResponse(matchId=match.id, action="like")

    elif body.action == "dislike":
        if match is not None:
            await db.delete(match)
            await db.commit()
        return ReactResponse(matchId=None, action="dislike")

    else:
        raise HTTPException(status_code=400, detail="action must be 'like' or 'dislike'")
