from fastapi import APIRouter, Depends, Request

from src.api.auth import verify_api_key
from src.api.schemas import (
    AddUserRequest,
    CommandResponse,
    QrBackupRequest,
    UserIdsRequest,
)


def _envelope(message: str) -> CommandResponse:
    return CommandResponse(ok=not message.startswith("❌"), message=message)


router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(verify_api_key)])


def _admin_chat_id(request: Request) -> int:
    # The handler enforces that requests come from the admin chat. The REST
    # API is already gated by the API key, so we present the staff chat id
    # to satisfy the same check without a second authorization mechanism.
    return request.app.state.config["telegram"]["staff_chat_id"]


@router.get("/default-users", response_model=CommandResponse)
async def get_default_users(request: Request):
    handler = request.app.state.admin_handler
    return _envelope(await handler.handle_get_default_users(_admin_chat_id(request)))


@router.put("/default-users", response_model=CommandResponse)
async def set_default_users(payload: UserIdsRequest, request: Request):
    handler = request.app.state.admin_handler
    return _envelope(await handler.handle_set_default_users(_admin_chat_id(request), payload.user_ids))


@router.post("/default-users", response_model=CommandResponse)
async def add_to_default_users(payload: UserIdsRequest, request: Request):
    handler = request.app.state.admin_handler
    return _envelope(await handler.handle_add_to_default_users(_admin_chat_id(request), payload.user_ids))


@router.delete("/default-users", response_model=CommandResponse)
async def remove_from_default_users(payload: UserIdsRequest, request: Request):
    handler = request.app.state.admin_handler
    return _envelope(await handler.handle_remove_from_default_users(_admin_chat_id(request), payload.user_ids))


@router.post("/users", response_model=CommandResponse)
async def add_user_to_db(payload: AddUserRequest, request: Request):
    handler = request.app.state.admin_handler
    return _envelope(await handler.handle_add_user_to_db(_admin_chat_id(request), payload.username))


@router.get("/qr-backup", response_model=CommandResponse)
async def get_qr_backup(request: Request):
    handler = request.app.state.admin_handler
    return _envelope(await handler.handle_get_qr_backup(_admin_chat_id(request)))


@router.put("/qr-backup", response_model=CommandResponse)
async def set_qr_backup(payload: QrBackupRequest, request: Request):
    handler = request.app.state.admin_handler
    return _envelope(await handler.handle_set_qr_backup(_admin_chat_id(request), payload.qr_data))


@router.get("/help", response_model=CommandResponse)
async def admin_help(request: Request):
    handler = request.app.state.admin_handler
    return _envelope(await handler.handle_admin_help(_admin_chat_id(request)))
