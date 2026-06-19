from typing import List, Optional
from pydantic import BaseModel, Field


class CommandResponse(BaseModel):
    """Generic envelope returned for command-style endpoints — mirrors the
    string the Telegram handler would have replied with, plus a parsed flag."""
    ok: bool
    message: str


class AddUserRequest(BaseModel):
    username: str = Field(..., min_length=1)


class CreateGroupRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = None
    user_ids: Optional[List[int]] = None
    full_admin: Optional[bool] = None


class AddUsersToGroupRequest(BaseModel):
    user_ids: List[int] = Field(..., min_items=1)


class UserIdsRequest(BaseModel):
    user_ids: List[int] = Field(..., min_items=1)


class QrBackupRequest(BaseModel):
    qr_data: str = Field(..., min_length=1)
