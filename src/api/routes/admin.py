import asyncio
import logging

from fastapi import APIRouter, Depends, Request
from fastapi import File, Form, Query, UploadFile

from src.api.auth import verify_api_key
from src.api.schemas import (
    AddUserRequest,
    CommandResponse,
    QrBackupRequest,
    QrGroupAssignmentRequest,
    QrSyncRequest,
    UserIdsRequest,
)


def _envelope(message: str) -> CommandResponse:
    return CommandResponse(ok=not message.startswith("❌"), message=message)


router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(verify_api_key)])
logger = logging.getLogger(__name__)


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
async def get_qr_backup(request: Request, qr_group: str = Query("default")):
    handler = request.app.state.admin_handler
    return _envelope(await handler.handle_get_qr_backup(_admin_chat_id(request), qr_group=qr_group))


@router.put("/qr-backup", response_model=CommandResponse)
async def set_qr_backup(payload: QrBackupRequest, request: Request):
    handler = request.app.state.admin_handler
    return _envelope(await handler.handle_set_qr_backup(
        _admin_chat_id(request),
        payload.qr_data,
        qr_group=payload.qr_group,
    ))


@router.post("/qr-backup/image", response_model=CommandResponse)
async def set_qr_backup_from_image(
    request: Request,
    qr_group: str = Form("default"),
    file: UploadFile = File(...),
):
    handler = request.app.state.admin_handler
    image_bytes = await file.read()
    return _envelope(await handler.handle_set_qr_backup_from_image(
        _admin_chat_id(request),
        image_bytes,
        qr_group=qr_group,
    ))


@router.get("/qr-groups", response_model=CommandResponse)
async def list_qr_groups(request: Request, qr_group: str = Query(None)):
    handler = request.app.state.admin_handler
    return _envelope(await handler.handle_list_qr_groups(_admin_chat_id(request), qr_group=qr_group))


@router.post("/qr-groups/{qr_group}/assignments", response_model=CommandResponse)
async def assign_qr_group(qr_group: str, payload: QrGroupAssignmentRequest, request: Request):
    handler = request.app.state.admin_handler
    return _envelope(await handler.handle_assign_qr_group(
        _admin_chat_id(request),
        qr_group,
        payload.group_ids,
    ))


@router.delete("/qr-groups/assignments", response_model=CommandResponse)
async def remove_qr_group_assignments(payload: QrGroupAssignmentRequest, request: Request):
    handler = request.app.state.admin_handler
    return _envelope(await handler.handle_remove_qr_group_assignment(
        _admin_chat_id(request),
        payload.group_ids,
    ))


@router.post("/qr-sync", response_model=CommandResponse)
async def sync_qr(payload: QrSyncRequest, request: Request):
    sync_group = (payload.qr_group or "default").strip().lower()
    current_task = request.app.state.api_background_tasks.get("grouphelp_qr_sync")
    if current_task and not current_task.done():
        return CommandResponse(ok=True, message="ℹ️ GroupHelp QR sync is already running.")

    group_service = request.app.state.group_handler.group_service

    async def run_sync():
        if sync_group == "all":
            await group_service.sync_all_grouphelp_qr_groups(delay_seconds=30)
        else:
            await group_service.sync_grouphelp_qr_to_owned_groups(
                delay_seconds=30,
                qr_group=sync_group,
            )

    def sync_done(task):
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("API GroupHelp QR sync failed: %s", e)
        finally:
            request.app.state.api_background_tasks["grouphelp_qr_sync"] = None

    task = asyncio.create_task(run_sync(), name="api-grouphelp-qr-sync")
    task.add_done_callback(sync_done)
    request.app.state.api_background_tasks["grouphelp_qr_sync"] = task
    return CommandResponse(ok=True, message=f"✅ GroupHelp QR sync `{sync_group}` started in background.")


@router.get("/help", response_model=CommandResponse)
async def admin_help(request: Request):
    handler = request.app.state.admin_handler
    return _envelope(await handler.handle_admin_help(_admin_chat_id(request)))
