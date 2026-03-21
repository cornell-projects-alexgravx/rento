from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


# --- Match ---

class MatchBase(BaseModel):
    user_id: str
    apartment_id: str
    status: str = "not_started"
    commute_minutes: Optional[int] = None
    match_score: Optional[float] = None
    match_reasoning: Optional[str] = None


class MatchCreate(MatchBase):
    pass


class MatchRead(MatchBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class MatchUpdate(BaseModel):
    status: Optional[str] = None
    commute_minutes: Optional[int] = None
    match_score: Optional[float] = None
    match_reasoning: Optional[str] = None


# --- Vote ---

class VoteBase(BaseModel):
    user_id: str
    apartment_id: str
    vote: str


class VoteCreate(VoteBase):
    pass


class VoteRead(VoteBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


class VoteUpdate(BaseModel):
    vote: Optional[str] = None
