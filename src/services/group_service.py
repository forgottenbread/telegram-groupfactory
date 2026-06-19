import logging
import asyncio
import re
from typing import Awaitable, Callable, List, Optional

from telethon import functions, types
from telethon.errors.rpcerrorlist import PeerFloodError, UserPrivacyRestrictedError
from telethon.tl.functions.channels import CreateChannelRequest, InviteToChannelRequest

from src.services.mongodb_service import MongoDBService
from src.config import (
    DEFAULT_QR_GROUP,
    get_default_group_users,
    get_qr_data,
    get_qr_group_assignments,
    list_qr_groups,
    normalize_qr_group_name,
)
from src.utils.qr_backup import build_qr_image

logger = logging.getLogger(__name__)

StatusCallback = Callable[[str], Awaitable[object]]
GROUPHELP_IMPORT_STATUS_RE = re.compile(r"🔀\s*Importazione Backup", re.IGNORECASE)
GROUPHELP_QR_DELETE_DELAY_SECONDS = 5
GROUPHELP_IMPORT_CLEANUP_WINDOW_SECONDS = 30
GROUPHELP_IMPORT_CLEANUP_POLL_SECONDS = 3

class GroupService:
    """Service class for group creation and management"""
    
    def __init__(self, mongo_service: MongoDBService, telegram_client=None):
        self.mongo_service = mongo_service
        self.client = telegram_client

    def set_client(self, telegram_client):
        self.client = telegram_client

    async def _notify(self, status_callback: Optional[StatusCallback], message: str):
        if status_callback:
            return await status_callback(message)
        return None

    def _sent_message_ids(self, sent_message) -> List[int]:
        if not sent_message:
            return []
        messages = sent_message if isinstance(sent_message, list) else [sent_message]
        return [message.id for message in messages if getattr(message, "id", None)]

    def _message_text(self, message) -> str:
        return (
            getattr(message, "raw_text", None)
            or getattr(message, "text", None)
            or getattr(message, "message", None)
            or ""
        )

    def _is_grouphelp_import_status(self, message) -> bool:
        return bool(GROUPHELP_IMPORT_STATUS_RE.search(self._message_text(message)))

    async def _delete_messages_safely(self, target_group, message_ids: List[int], reason: str) -> int:
        if not message_ids:
            return 0
        try:
            await self.client.delete_messages(target_group, message_ids, revoke=True)
            logger.info("Deleted %s message(s): %s", reason, message_ids)
            return len(message_ids)
        except Exception as e:
            logger.warning("Failed to delete %s message(s) %s: %s", reason, message_ids, e)
            return 0

    async def _cleanup_grouphelp_import_artifacts(self, target_group, sent_message, qr_group: str):
        sent_ids = self._sent_message_ids(sent_message)
        min_message_id = min(sent_ids) if sent_ids else 0

        await asyncio.sleep(GROUPHELP_QR_DELETE_DELAY_SECONDS)
        await self._delete_messages_safely(target_group, sent_ids, "GroupHelp QR import")

        deleted_status_ids = set()
        deadline = asyncio.get_running_loop().time() + GROUPHELP_IMPORT_CLEANUP_WINDOW_SECONDS
        while asyncio.get_running_loop().time() < deadline:
            status_ids = []
            try:
                async for message in self.client.iter_messages(target_group, limit=20):
                    message_id = getattr(message, "id", None)
                    if not message_id or message_id in deleted_status_ids:
                        continue
                    if min_message_id and message_id < min_message_id:
                        continue
                    if self._is_grouphelp_import_status(message):
                        status_ids.append(message_id)
            except Exception as e:
                logger.warning("Failed to scan GroupHelp import status messages for %s: %s", qr_group, e)
                return

            if status_ids:
                await self._delete_messages_safely(target_group, status_ids, "GroupHelp import status")
                deleted_status_ids.update(status_ids)

            await asyncio.sleep(GROUPHELP_IMPORT_CLEANUP_POLL_SECONDS)

    def _log_background_task_result(self, task: asyncio.Task):
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Background GroupHelp cleanup failed: %s", e)

    def _schedule_grouphelp_import_cleanup(self, target_group, sent_message, qr_group: str):
        task = asyncio.create_task(
            self._cleanup_grouphelp_import_artifacts(target_group, sent_message, qr_group),
            name=f"grouphelp-import-cleanup-{qr_group}",
        )
        task.add_done_callback(self._log_background_task_result)
        return task

    async def _send_grouphelp_qr_import(self, target_group, qr_data: str, qr_group: str = DEFAULT_QR_GROUP):
        qr_image = build_qr_image(qr_data)
        sent_message = await self.client.send_file(
            target_group,
            qr_image,
            caption=".importbackup",
            force_document=False,
        )
        return self._schedule_grouphelp_import_cleanup(target_group, sent_message, qr_group)

    async def _edit_status(self, status_message, message: str):
        if hasattr(status_message, "edit"):
            await status_message.edit(message)
        else:
            await self.client.edit_message(status_message, message)

    def _admin_rights(self, **rights):
        try:
            return types.ChatAdminRights(**rights)
        except TypeError:
            rights.pop("manage_topics", None)
            return types.ChatAdminRights(**rights)

    async def _promote_user(self, channel, user_id, full_admin: bool):
        if full_admin:
            admin_rights = self._admin_rights(
                change_info=True,
                post_messages=True,
                edit_messages=True,
                delete_messages=True,
                ban_users=True,
                invite_users=True,
                pin_messages=True,
                add_admins=True,
                anonymous=False,
                manage_call=True,
                other=True,
                manage_topics=True,
            )
            rank = "manager"
        else:
            admin_rights = self._admin_rights(
                change_info=False,
                post_messages=True,
                edit_messages=True,
                delete_messages=True,
                ban_users=True,
                invite_users=True,
                pin_messages=True,
                add_admins=False,
                anonymous=False,
                manage_call=True,
                other=False,
                manage_topics=True,
            )
            rank = "admin"

        await self.client(functions.channels.EditAdminRequest(
            channel=channel,
            user_id=user_id,
            admin_rights=admin_rights,
            rank=rank,
        ))

    async def _export_invite_link(self, channel) -> Optional[str]:
        try:
            invite = await self.client(functions.messages.ExportChatInviteRequest(
                peer=channel,
            ))
            return getattr(invite, "link", None)
        except Exception as e:
            logger.warning(f"Failed to export invite link: {e}")
            return None

    def _is_owned_group_dialog(self, dialog) -> bool:
        entity = getattr(dialog, "entity", None)
        if not entity or not getattr(dialog, "is_group", False):
            return False
        if getattr(entity, "broadcast", False):
            return False
        return bool(getattr(entity, "creator", False))

    def _dialog_assignment_keys(self, dialog) -> List[str]:
        keys = {str(getattr(dialog, "id", ""))}
        entity = getattr(dialog, "entity", None)
        entity_id = getattr(entity, "id", None)
        if entity_id is not None:
            keys.add(str(entity_id))
            keys.add(f"-100{entity_id}")
        return [key for key in keys if key]

    def _dialog_assignment_group(self, dialog, assignments: dict) -> Optional[str]:
        for key in self._dialog_assignment_keys(dialog):
            assignment = assignments.get(key)
            if assignment:
                return assignment.get("group")
        return None

    def _user_label(self, user) -> str:
        if user.username:
            return f"@{user.username}"
        return str(user.id)

    def _save_resolved_access_hash(self, user, input_user) -> None:
        access_hash = getattr(input_user, "access_hash", None)
        user_id = getattr(input_user, "user_id", None) or getattr(input_user, "id", None)
        if access_hash and user_id:
            user.id = user_id
            user.access_hash = access_hash
            self.mongo_service.save_user(user)

    async def _resolve_input_user(self, user):
        references = []
        if user.username:
            references.append(user.username)
        if user.access_hash:
            references.append(types.InputUser(user.id, user.access_hash))
        references.append(user.id)

        last_error = None
        for reference in references:
            try:
                input_user = await self.client.get_input_entity(reference)
                self._save_resolved_access_hash(user, input_user)
                access_hash = getattr(input_user, "access_hash", None)
                user_id = getattr(input_user, "user_id", None) or getattr(input_user, "id", None)
                if access_hash and user_id:
                    return types.InputUser(user_id, access_hash)
                return input_user
            except ValueError as e:
                last_error = e

        if not user.username and not user.access_hash:
            raise ValueError(
                "numeric ID has no stored access_hash. Add this user by @username "
                "or use /admin_add_user or /admin_add_users with no args and "
                "forward a user message."
            ) from last_error
        raise last_error or ValueError("could not resolve Telegram user")

    async def create_group(
        self,
        group_name: str,
        description: str = "",
        user_ids: List[int] = None,
        status_callback: Optional[StatusCallback] = None,
        staff_chat_id: Optional[int] = None,
        factory_bot_id: Optional[int] = None,
        factory_bot_username: Optional[str] = None,
    ) -> Optional[dict]:
        """Create a Telegram megagroup and run the IMS GroupFactory setup flow."""
        try:
            if not self.client:
                logger.error("Telegram client not initialized")
                return None

            await self._notify(status_callback, f'🚀 Creating group "{group_name}"...')
            created_channel = await self.client(CreateChannelRequest(
                group_name,
                description,
                megagroup=True,
                broadcast=False,
            ))

            channel = created_channel.chats[0]
            target_group = types.InputPeerChannel(channel.id, channel.access_hash)
            await self._notify(status_callback, f'✅ Group "{group_name}" created successfully!')
            
            if user_ids is None or len(user_ids) == 0:
                user_ids = get_default_group_users()
                if len(user_ids) == 0:
                    logger.warning("No default users configured for group creation")
            
            users = []
            for user_id in user_ids:
                user = self.mongo_service.get_user_by_id(user_id)
                if user:
                    users.append(user)
                else:
                    logger.warning(f"User {user_id} not found in database")
            
            await self._notify(status_callback, f"👥 Found {len(users)} configured users to add")
            status_message = await self._notify(status_callback, "👥 Adding users to the group...")
            success_count = 0
            error_count = 0

            for index, user in enumerate(users):
                try:
                    if index % 5 == 0 and status_message:
                        await self._edit_status(
                            status_message,
                            f"👥 Adding users: {index}/{len(users)} completed",
                        )

                    user_ref = self._user_label(user)
                    user_to_add = await self._resolve_input_user(user)
                    await self.client(InviteToChannelRequest(target_group, [user_to_add]))
                    await self._promote_user(target_group, user_to_add, full_admin=False)
                    success_count += 1
                    await asyncio.sleep(2)

                except PeerFloodError:
                    logger.warning("Telegram flood limit reached while adding users")
                    await self._notify(status_callback, "⚠️ Telegram flood limit reached. Pausing for 30 seconds...")
                    await asyncio.sleep(30)
                except UserPrivacyRestrictedError:
                    logger.warning(f"User {self._user_label(user)} has privacy restrictions")
                    error_count += 1
                except ValueError as e:
                    logger.error(f"Could not resolve Telegram entity for user {self._user_label(user)}: {e}")
                    await self._notify(
                        status_callback,
                        f"⚠️ Could not resolve user {self._user_label(user)}: {e}"
                    )
                    error_count += 1
                except Exception as e:
                    logger.error(f"Error adding user {self._user_label(user)}: {e}")
                    error_count += 1
                    if error_count > 10:
                        await self._notify(status_callback, "❌ Too many errors, aborting user addition!")
                        return None

            if status_message:
                await self._edit_status(
                    status_message,
                    f"✅ Added {success_count}/{len(users)} users to the group",
                )

            factory_bot_username = (factory_bot_username or "").strip().lstrip("@")
            factory_bot_ref = factory_bot_username or factory_bot_id
            if factory_bot_ref:
                try:
                    logger.info(f"Promoting factory bot {factory_bot_ref} as manager")
                    factory_bot = await self.client.get_input_entity(factory_bot_ref)
                    try:
                        await self.client(InviteToChannelRequest(target_group, [factory_bot]))
                    except Exception as e:
                        logger.info(f"Factory bot invite skipped or failed before promotion: {e}")
                    await self._promote_user(target_group, factory_bot, full_admin=True)
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"Failed to promote factory bot {factory_bot_ref}: {e}")
                    if factory_bot_username:
                        await self._notify(status_callback, f"⚠️ Failed to promote factory bot @{factory_bot_username}: {e}")
                    else:
                        await self._notify(
                            status_callback,
                            "⚠️ Failed to promote factory bot from FACTORY_BOT_ID. "
                            "Set FACTORY_BOT_USERNAME so Telethon can resolve the bot entity."
                        )

            await self._notify(status_callback, "⚙️ Sending GroupHelp setup commands...")
            await self.client.send_message(target_group, "/pro")
            await asyncio.sleep(2)
            if staff_chat_id:
                await self.client.send_message(target_group, f"/setstaffgroup {staff_chat_id}")
                await asyncio.sleep(2)

            qr_imported = False
            qr_data = get_qr_data()
            if qr_data:
                logger.info("Sending GroupHelp QR backup import image")
                await self._send_grouphelp_qr_import(target_group, qr_data)
                qr_imported = True
                if staff_chat_id:
                    await self.client.send_message(staff_chat_id, "✅ GroupHelp QR backup image sent to the new group.")
            elif staff_chat_id:
                await self.client.send_message(staff_chat_id, "⚠️ No GroupHelp QR backup data configured. Use `/admin_set_qr <qr_payload>`.")

            invite_link = await self._export_invite_link(target_group)
            if staff_chat_id:
                if invite_link:
                    await self.client.send_message(staff_chat_id, f"🔗 Invite link:\n\n{invite_link}")
                else:
                    await self.client.send_message(staff_chat_id, "⚠️ Failed to generate invite link")

            logger.info(f"Group creation process completed for {group_name}")
            return {
                "id": channel.id,
                "access_hash": channel.access_hash,
                "title": channel.title,
                "invite_link": invite_link,
                "users_added": success_count,
                "users_total": len(users),
                "qr_imported": qr_imported,
            }
                
        except Exception as e:
            logger.error(f"Error creating group '{group_name}': {e}")
            return None

    async def sync_grouphelp_qr_to_owned_groups(
        self,
        status_callback: Optional[StatusCallback] = None,
        delay_seconds: int = 30,
        qr_group: str = DEFAULT_QR_GROUP,
    ) -> dict:
        """Send stored GroupHelp QR backup to every group owned by the userbot."""
        if not self.client:
            logger.error("Telegram client not initialized")
            return {
                "matched": 0,
                "sent": 0,
                "failed": 0,
                "skipped": 0,
                "errors": ["Telegram client not initialized"],
            }

        group = normalize_qr_group_name(qr_group)
        qr_data = get_qr_data(group)
        if not qr_data:
            await self._notify(status_callback, f"❌ No GroupHelp QR backup data configured for `{group}`. Use `/admin_set_qr {group} <qr_payload>`.")
            return {
                "matched": 0,
                "sent": 0,
                "failed": 0,
                "skipped": 0,
                "errors": [f"No GroupHelp QR backup data configured for {group}"],
            }

        sent = 0
        failed = 0
        skipped = 0
        errors = []
        owned_groups = []
        cleanup_tasks = []
        assignments = get_qr_group_assignments()

        async for dialog in self.client.iter_dialogs():
            if not self._is_owned_group_dialog(dialog):
                continue
            assignment_group = self._dialog_assignment_group(dialog, assignments)
            if group == DEFAULT_QR_GROUP:
                if assignment_group not in (None, DEFAULT_QR_GROUP):
                    skipped += 1
                    continue
            elif assignment_group != group:
                skipped += 1
                continue
            owned_groups.append(dialog)

        matched = len(owned_groups)
        if matched == 0:
            await self._notify(status_callback, f"⚠️ No owned groups found for GroupHelp QR sync group `{group}`.")
            return {
                "matched": matched,
                "sent": sent,
                "failed": failed,
                "skipped": skipped,
                "errors": errors,
            }

        await self._notify(status_callback, f"🔄 Starting GroupHelp QR sync for `{group}` across {matched} owned groups...")

        for index, dialog in enumerate(owned_groups):
            group_name = getattr(dialog, "name", None) or getattr(dialog.entity, "title", None) or str(dialog.id)

            try:
                logger.info("Sending stored GroupHelp QR backup %s to owned group %s", group, group_name)
                cleanup_tasks.append(
                    await self._send_grouphelp_qr_import(dialog.entity, qr_data, qr_group=group)
                )
                sent += 1
                await self._notify(
                    status_callback,
                    f"✅ Sent GroupHelp QR `{group}` to {group_name} ({index + 1}/{matched})",
                )
            except Exception as e:
                failed += 1
                error = f"{group_name}: {e}"
                errors.append(error)
                logger.error("Failed to send GroupHelp QR backup %s to %s: %s", group, group_name, e)
                await self._notify(status_callback, f"⚠️ Failed to send GroupHelp QR `{group}` to {group_name}: {e}")

            if index < matched - 1:
                await asyncio.sleep(delay_seconds)

        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)

        await self._notify(
            status_callback,
            f"✅ GroupHelp QR sync for `{group}` complete. Sent: {sent}, failed: {failed}, owned groups: {matched}.",
        )

        return {
            "matched": matched,
            "sent": sent,
            "failed": failed,
            "skipped": skipped,
            "errors": errors,
        }

    async def sync_all_grouphelp_qr_groups(
        self,
        status_callback: Optional[StatusCallback] = None,
        delay_seconds: int = 30,
    ) -> dict:
        """Sync every configured logical GroupHelp QR group sequentially."""
        groups = list_qr_groups(include_assignments=True)
        if DEFAULT_QR_GROUP not in groups:
            groups.insert(0, DEFAULT_QR_GROUP)

        totals = {
            "groups": [],
            "matched": 0,
            "sent": 0,
            "failed": 0,
            "skipped": 0,
            "errors": [],
        }

        for index, group in enumerate(groups):
            result = await self.sync_grouphelp_qr_to_owned_groups(
                status_callback=status_callback,
                delay_seconds=delay_seconds,
                qr_group=group,
            )
            totals["groups"].append(group)
            totals["matched"] += result.get("matched", 0)
            totals["sent"] += result.get("sent", 0)
            totals["failed"] += result.get("failed", 0)
            totals["skipped"] += result.get("skipped", 0)
            totals["errors"].extend(result.get("errors", []))
            if index < len(groups) - 1:
                await asyncio.sleep(delay_seconds if result.get("matched", 0) > 0 else 1)

        await self._notify(
            status_callback,
            f"✅ All GroupHelp QR syncs complete. Groups: {len(groups)}, sent: {totals['sent']}, failed: {totals['failed']}.",
        )
        return totals
    
    async def add_users_to_group(self, group_id: str, user_ids: List[int]) -> bool:
        """Add users to an existing Telegram group"""
        try:
            if not self.client:
                logger.error("Telegram client not initialized")
                return False
            
            users = []
            for user_id in user_ids:
                user = self.mongo_service.get_user_by_id(user_id)
                if user:
                    users.append(user)
                else:
                    logger.warning(f"User {user_id} not found in database")
            
            if not users:
                logger.warning("No valid users found for adding to group")
                return False
            
            group = await self.client.get_input_entity(group_id)
            for user in users:
                user_ref = self._user_label(user)
                try:
                    user_to_add = await self._resolve_input_user(user)
                    await self.client(InviteToChannelRequest(group, [user_to_add]))
                except ValueError as e:
                    logger.error(f"Could not resolve Telegram entity for user {user_ref}: {e}")
                    return False

            logger.info(f"Successfully added {len(users)} users to group {group_id}")
            return True
                
        except Exception as e:
            logger.error(f"Error adding users to group {group_id}: {e}")
            return False
    
    async def get_group_info(self, group_id: str) -> Optional[dict]:
        """Get information about a Telegram group"""
        try:
            if not self.client:
                logger.error("Telegram client not initialized")
                return None
            
            result = await self.client.get_entity(group_id)
            logger.info(f"Retrieved information for group {group_id}")
            return {
                "id": getattr(result, "id", None),
                "title": getattr(result, "title", None),
                "username": getattr(result, "username", None),
            }
                
        except Exception as e:
            logger.error(f"Error retrieving group info for {group_id}: {e}")
            return None
