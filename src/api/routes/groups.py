from fastapi import APIRouter, Depends, Request

from src.api.auth import verify_api_key
from src.api.schemas import (
    AddUsersToGroupRequest,
    CommandResponse,
    CreateGroupRequest,
)
from src.config import save_user_admin_role


def _envelope(message: str) -> CommandResponse:
    return CommandResponse(ok=not message.startswith("❌"), message=message)


router = APIRouter(prefix="/api/groups", tags=["groups"], dependencies=[Depends(verify_api_key)])


@router.post("", response_model=CommandResponse)
async def create_group(payload: CreateGroupRequest, request: Request):
    handler = request.app.state.group_handler
    message = await handler.handle_create_group(payload.name, payload.user_ids)

    # Mirror the Telegram inline-button flow: persist the admin-role choice
    # against the bot user (the entity creating the group via the API).
    if payload.full_admin is not None:
        bot_user_id = request.app.state.config["telegram"].get("factory_bot_id")
        if bot_user_id:
            save_user_admin_role(bot_user_id, payload.full_admin)

    return _envelope(message)


@router.get("/{group_id}", response_model=CommandResponse)
async def get_group(group_id: str, request: Request):
    handler = request.app.state.group_handler
    return _envelope(await handler.handle_get_group_info(group_id))


@router.post("/{group_id}/users", response_model=CommandResponse)
async def add_users_to_group(group_id: str, payload: AddUsersToGroupRequest, request: Request):
    handler = request.app.state.group_handler
    return _envelope(await handler.handle_add_users(group_id, payload.user_ids))
