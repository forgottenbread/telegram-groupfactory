import logging
import asyncio
from typing import Awaitable, Callable, List, Optional

from telethon import functions, types
from telethon.errors.rpcerrorlist import PeerFloodError, UserPrivacyRestrictedError
from telethon.tl.functions.channels import CreateChannelRequest, InviteToChannelRequest

from src.services.mongodb_service import MongoDBService
from src.config import get_default_group_users, get_qr_data

logger = logging.getLogger(__name__)

StatusCallback = Callable[[str], Awaitable[object]]

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

    def _build_importbackup_message(self, qr_data: str) -> str:
        qr_data = qr_data.strip()
        if qr_data.lower().startswith((".importbackup", "/importbackup")):
            return qr_data
        return f".importbackup {qr_data}"
    
    async def create_group(
        self,
        group_name: str,
        description: str = "",
        user_ids: List[int] = None,
        status_callback: Optional[StatusCallback] = None,
        staff_chat_id: Optional[int] = None,
        factory_bot_id: Optional[int] = None,
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

                    user_ref = user.username or user.id
                    user_to_add = await self.client.get_input_entity(user_ref)
                    await self.client(InviteToChannelRequest(target_group, [user_to_add]))
                    await self._promote_user(target_group, user_to_add, full_admin=False)
                    success_count += 1
                    await asyncio.sleep(2)

                except PeerFloodError:
                    logger.warning("Telegram flood limit reached while adding users")
                    await self._notify(status_callback, "⚠️ Telegram flood limit reached. Pausing for 30 seconds...")
                    await asyncio.sleep(30)
                except UserPrivacyRestrictedError:
                    logger.warning(f"User {user.username or user.id} has privacy restrictions")
                    error_count += 1
                except Exception as e:
                    logger.error(f"Error adding user {user.username or user.id}: {e}")
                    error_count += 1
                    if error_count > 10:
                        await self._notify(status_callback, "❌ Too many errors, aborting user addition!")
                        return None

            if status_message:
                await self._edit_status(
                    status_message,
                    f"✅ Added {success_count}/{len(users)} users to the group",
                )

            if factory_bot_id:
                try:
                    logger.info(f"Promoting factory bot {factory_bot_id} as manager")
                    factory_bot = await self.client.get_input_entity(factory_bot_id)
                    try:
                        await self.client(InviteToChannelRequest(target_group, [factory_bot]))
                    except Exception as e:
                        logger.info(f"Factory bot invite skipped or failed before promotion: {e}")
                    await self._promote_user(target_group, factory_bot, full_admin=True)
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"Failed to promote factory bot {factory_bot_id}: {e}")
                    await self._notify(status_callback, f"⚠️ Failed to promote factory bot: {e}")

            await self._notify(status_callback, "⚙️ Sending GroupHelp setup commands...")
            await self.client.send_message(target_group, "/pro")
            await asyncio.sleep(2)
            if staff_chat_id:
                await self.client.send_message(target_group, f"/setstaffgroup {staff_chat_id}")
                await asyncio.sleep(2)

            qr_imported = False
            qr_data = get_qr_data()
            if qr_data:
                logger.info("Sending GroupHelp QR backup import command")
                await self.client.send_message(
                    target_group,
                    self._build_importbackup_message(qr_data),
                )
                qr_imported = True
                if staff_chat_id:
                    await self.client.send_message(staff_chat_id, "✅ GroupHelp QR backup import sent to the new group.")
            elif staff_chat_id:
                await self.client.send_message(staff_chat_id, "⚠️ No GroupHelp QR backup data configured. Use `/admin_set_qr <qr_data>`.")

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
                user_ref = user.username or user.id
                user_to_add = await self.client.get_input_entity(user_ref)
                await self.client(InviteToChannelRequest(group, [user_to_add]))

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
