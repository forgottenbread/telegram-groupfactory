from fastapi import APIRouter, Depends, Request

from src.api.auth import verify_api_key
from src.api.schemas import AddUserRequest, CommandResponse


def _envelope(message: str) -> CommandResponse:
    return CommandResponse(ok=not message.startswith("❌"), message=message)


router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(verify_api_key)])


@router.get("", response_model=CommandResponse)
async def list_users(request: Request):
    handler = request.app.state.user_handler
    return _envelope(handler.handle_get_all_users())


@router.get("/{user_id}", response_model=CommandResponse)
async def get_user(user_id: int, request: Request):
    handler = request.app.state.user_handler
    return _envelope(handler.handle_get_user_by_id(user_id))


@router.post("", response_model=CommandResponse)
async def add_user(payload: AddUserRequest, request: Request):
    handler = request.app.state.user_handler
    return _envelope(handler.handle_add_user(payload.username))


@router.delete("/{user_id}", response_model=CommandResponse)
async def delete_user(user_id: int, request: Request):
    handler = request.app.state.user_handler
    return _envelope(handler.handle_delete_user(user_id))
