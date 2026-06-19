from fastapi import APIRouter, Depends, Request

from src.api.auth import verify_api_key
from src.api.schemas import (
    AddUsersToGroupRequest,
    CommandResponse,
    CreateGroupRequest,
)


def _envelope(message: str) -> CommandResponse:
    return CommandResponse(ok=not message.startswith("❌"), message=message)


router = APIRouter(prefix="/api/groups", tags=["groups"], dependencies=[Depends(verify_api_key)])


@router.post("", response_model=CommandResponse)
async def create_group(payload: CreateGroupRequest, request: Request):
    handler = request.app.state.group_handler
    message = await handler.handle_create_group(
        payload.name,
        user_ids=payload.user_ids,
        description=payload.description or payload.name,
        staff_chat_id=request.app.state.config["telegram"].get("staff_chat_id"),
        factory_bot_id=request.app.state.config["telegram"].get("factory_bot_id"),
        factory_bot_username=request.app.state.config["telegram"].get("factory_bot_username"),
    )

    return _envelope(message)


@router.get("/{group_id}", response_model=CommandResponse)
async def get_group(group_id: str, request: Request):
    handler = request.app.state.group_handler
    return _envelope(await handler.handle_get_group_info(group_id))


@router.post("/{group_id}/users", response_model=CommandResponse)
async def add_users_to_group(group_id: str, payload: AddUsersToGroupRequest, request: Request):
    handler = request.app.state.group_handler
    return _envelope(await handler.handle_add_users(group_id, payload.user_ids))
