import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.match import Match
from app.schemas.match import MatchCreate, MatchRead, MatchUpdate

router = APIRouter(tags=["matches"])


@router.get("/matches", response_model=List[MatchRead])
async def list_matches(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Match).offset(skip).limit(limit))
    return result.scalars().all()


@router.get("/matches/{match_id}", response_model=MatchRead)
async def get_match(match_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Match, match_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Match not found")
    return obj


@router.post("/matches", response_model=MatchRead, status_code=201)
async def create_match(body: MatchCreate, db: AsyncSession = Depends(get_db)):
    obj = Match(id=str(uuid.uuid4()), **body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.patch("/matches/{match_id}", response_model=MatchRead)
async def update_match(match_id: str, body: MatchUpdate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Match, match_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Match not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/matches/{match_id}", status_code=204)
async def delete_match(match_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Match, match_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Match not found")
    await db.delete(obj)
    await db.commit()


@router.get("/users/{user_id}/matches", response_model=List[MatchRead])
async def get_user_matches(user_id: str, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Match).where(Match.user_id == user_id).offset(skip).limit(limit)
    )
    return result.scalars().all()
