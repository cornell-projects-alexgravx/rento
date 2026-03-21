import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.match import Vote
from app.schemas.match import VoteCreate, VoteRead, VoteUpdate

router = APIRouter(tags=["votes"])


@router.get("/votes", response_model=List[VoteRead])
async def list_votes(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Vote).offset(skip).limit(limit))
    return result.scalars().all()


@router.get("/votes/{vote_id}", response_model=VoteRead)
async def get_vote(vote_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Vote, vote_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Vote not found")
    return obj


@router.post("/votes", response_model=VoteRead, status_code=201)
async def create_vote(body: VoteCreate, db: AsyncSession = Depends(get_db)):
    obj = Vote(id=str(uuid.uuid4()), **body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.patch("/votes/{vote_id}", response_model=VoteRead)
async def update_vote(vote_id: str, body: VoteUpdate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Vote, vote_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Vote not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/votes/{vote_id}", status_code=204)
async def delete_vote(vote_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Vote, vote_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Vote not found")
    await db.delete(obj)
    await db.commit()


@router.get("/users/{user_id}/votes", response_model=List[VoteRead])
async def get_user_votes(user_id: str, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Vote).where(Vote.user_id == user_id).offset(skip).limit(limit)
    )
    return result.scalars().all()
