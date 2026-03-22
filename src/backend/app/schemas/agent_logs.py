from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


# --- Agent1Log ---

class Agent1LogBase(BaseModel):
    apartment_id: str
    source: Optional[str] = None
    content: str
    result: Optional[str] = None


class Agent1LogCreate(Agent1LogBase):
    pass


class Agent1LogRead(Agent1LogBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    timestamp: datetime


class Agent1LogUpdate(BaseModel):
    source: Optional[str] = None
    content: Optional[str] = None
    result: Optional[str] = None


# --- Agent2Log ---

class Agent2LogBase(BaseModel):
    user_id: str
    content: str
    result: Optional[str] = None


class Agent2LogCreate(Agent2LogBase):
    pass


class Agent2LogRead(Agent2LogBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    timestamp: datetime


class Agent2LogUpdate(BaseModel):
    content: Optional[str] = None
    result: Optional[str] = None


# --- Agent3Log ---

class Agent3LogBase(BaseModel):
    user_id: str
    apartment_id: Optional[str] = None
    message_id: Optional[str] = None
    content: Optional[str] = None
    result: Optional[str] = None


class Agent3LogCreate(Agent3LogBase):
    pass


class Agent3LogRead(Agent3LogBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    timestamp: datetime


class Agent3LogUpdate(BaseModel):
    apartment_id: Optional[str] = None
    message_id: Optional[str] = None
    content: Optional[str] = None
    result: Optional[str] = None
