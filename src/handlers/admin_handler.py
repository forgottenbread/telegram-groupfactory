import logging
from typing import List
from src.config import (
    get_default_group_users, set_default_group_users, get_qr_data, 
    set_qr_backup_data, verify_admin_access
)
from src.services.user_service import UserService
from src.models.user import User
from src.utils.qr_backup import decode_qr_image_payload, normalize_qr_payload

logger = logging.getLogger(__name__)

class AdminHandler:
    """Handler class for admin configuration commands"""
    
    def __init__(self, user_service: UserService, telegram_client=None):
        self.user_service = user_service
        self.telegram_client = telegram_client

    def set_client(self, telegram_client):
        self.telegram_client = telegram_client

    def _ensure_user_record(self, user_id: int) -> tuple:
        user = self.user_service.get_user_by_id(user_id)
        if user:
            return user, False

        user = User(id=user_id, username=None, first_name=f"id:{user_id}")
        saved = self.user_service.save_user(user)
        if not saved:
            raise RuntimeError(f"Failed to create placeholder user record for {user_id}")
        return user, True

    def _format_user(self, user: User, user_id: int, created: bool = False) -> str:
        notes = []
        if created:
            notes.append("placeholder created")
        if not user.username and not user.access_hash:
            notes.append("not inviteable yet")
        created_note = f" ({', '.join(notes)})" if notes else ""
        username = f"@{user.username}" if user.username else user.name
        return f"  • {username} (ID: {user_id}){created_note}"

    def _uninviteable_user_ids(self, user_ids: List[int]) -> List[int]:
        missing = []
        for user_id in user_ids:
            user = self.user_service.get_user_by_id(user_id)
            if user and not user.username and not user.access_hash:
                missing.append(user_id)
        return missing

    def _append_uninviteable_warning(self, response: str, user_ids: List[int]) -> str:
        missing = self._uninviteable_user_ids(user_ids)
        if missing:
            response += (
                "\n\n⚠️ These numeric IDs are stored but not inviteable yet: "
                f"{missing}. Re-add them with @username, or run `/admin_add_user` "
                "or `/admin_add_users` with no args and forward a user message "
                "so Telegram access_hash can be stored."
            )
        return response

    def _is_numeric_id(self, value) -> bool:
        return str(value).strip().lstrip("-").isdigit()

    def _user_from_entity(self, entity, fallback_username: str = None) -> User:
        username = getattr(entity, "username", None) or fallback_username
        return User(
            id=entity.id,
            username=username.lstrip("@") if username else None,
            first_name=getattr(entity, "first_name", None) or getattr(entity, "title", None),
            last_name=getattr(entity, "last_name", None),
            access_hash=getattr(entity, "access_hash", None),
        )

    def _save_user_entity(self, entity, fallback_username: str = None) -> tuple:
        user = self._user_from_entity(entity, fallback_username=fallback_username)
        existed = self.user_service.get_user_by_id(user.id) is not None
        if not self.user_service.save_user(user):
            raise RuntimeError(f"Failed to save user {user.id}")
        return user.id, user, not existed

    async def _resolve_user_identifier(self, identifier) -> tuple:
        identifier = str(identifier).strip().rstrip(",")
        if not identifier:
            raise ValueError("Empty user identifier")

        if self._is_numeric_id(identifier):
            user_id = int(identifier)
            if self.telegram_client:
                try:
                    entity = await self.telegram_client.get_entity(user_id)
                    return self._save_user_entity(entity)
                except Exception as e:
                    logger.info("Could not resolve numeric user ID %s, creating placeholder: %s", user_id, e)
            user, created = self._ensure_user_record(user_id)
            return user_id, user, created

        if not self.telegram_client:
            raise RuntimeError("Telegram client is required to resolve usernames")

        username = identifier.lstrip("@")
        entity = await self.telegram_client.get_entity(username)
        return self._save_user_entity(entity, fallback_username=username)

    async def _resolve_user_identifiers(self, identifiers: List) -> tuple:
        resolved = []
        created_users = []
        errors = []

        for identifier in identifiers:
            try:
                user_id, _, created = await self._resolve_user_identifier(identifier)
                resolved.append(user_id)
                if created:
                    created_users.append(user_id)
            except Exception as e:
                logger.error(f"Failed to resolve user identifier {identifier}: {e}")
                errors.append(f"{identifier}: {e}")

        return resolved, created_users, errors
    
    def verify_access(self, chat_id: int) -> tuple:
        """Verify admin access"""
        return verify_admin_access(chat_id)
    
    async def handle_get_default_users(self, chat_id: int) -> str:
        """Get current default users for new groups (Admin only)"""
        is_admin, error = self.verify_access(chat_id)
        if not is_admin:
            return error
        
        try:
            default_users = get_default_group_users()
            if not default_users:
                return "📋 No default users configured yet.\n\nUse `/admin_set_users <id_or_username1> <id_or_username2> ...` to configure them."
            
            user_list = []
            for user_id in default_users:
                user = self.user_service.get_user_by_id(user_id)
                if user:
                    user_list.append(self._format_user(user, user_id))
                else:
                    user_list.append(f"  • Unknown User (ID: {user_id})")
            
            return "📋 Current default users for new groups:\n" + "\n".join(user_list)
        except Exception as e:
            logger.error(f"Error getting default users: {e}")
            return f"❌ Error retrieving default users: {str(e)}"
    
    async def handle_set_default_users(self, chat_id: int, user_ids: List) -> str:
        """Set default users for new groups (Admin only)"""
        is_admin, error = self.verify_access(chat_id)
        if not is_admin:
            return error
        
        try:
            if not user_ids:
                return "❌ Please provide at least one user ID or username.\n\nUsage: `/admin_set_users <id_or_username1> <id_or_username2> ...`"
            
            valid_user_ids, created_users, errors = await self._resolve_user_identifiers(user_ids)
            if not valid_user_ids:
                return "❌ No valid users could be resolved.\n" + "\n".join(errors)
            
            # Set default users
            if set_default_group_users(valid_user_ids):
                user_list = []
                for user_id in valid_user_ids:
                    user = self.user_service.get_user_by_id(user_id)
                    if user:
                        user_list.append(self._format_user(user, user_id, user_id in created_users))
                
                response = "✅ Default users updated successfully:\n" + "\n".join(user_list)
                if created_users:
                    response += "\n\nℹ️ New user records were created."
                if errors:
                    response += "\n\n⚠️ Some identifiers could not be resolved:\n" + "\n".join(errors)
                response = self._append_uninviteable_warning(response, valid_user_ids)
                
                return response
            else:
                return "❌ Failed to save default users configuration"
        except Exception as e:
            logger.error(f"Error setting default users: {e}")
            return f"❌ Error setting default users: {str(e)}"
    
    async def handle_add_to_default_users(self, chat_id: int, user_ids: List) -> str:
        """Add users to existing default users list (Admin only)"""
        is_admin, error = self.verify_access(chat_id)
        if not is_admin:
            return error
        
        try:
            if not user_ids:
                return "❌ Please provide at least one user ID or username.\n\nUsage: `/admin_add_users <id_or_username1> <id_or_username2> ...`"
            
            current_users = get_default_group_users()
            
            resolved_user_ids, created_users, errors = await self._resolve_user_identifiers(user_ids)
            valid_user_ids = [user_id for user_id in resolved_user_ids if user_id not in current_users]
            
            if not valid_user_ids:
                response = "ℹ️ All resolved users are already in the default list."
                if errors:
                    response += "\n\n⚠️ Some identifiers could not be resolved:\n" + "\n".join(errors)
                return response
            
            # Add to default users
            updated_users = current_users + valid_user_ids
            if set_default_group_users(updated_users):
                user_list = []
                for user_id in valid_user_ids:
                    user = self.user_service.get_user_by_id(user_id)
                    if user:
                        user_list.append(self._format_user(user, user_id, user_id in created_users))
                
                response = "✅ Users added to default list:\n" + "\n".join(user_list)
                if created_users:
                    response += "\n\nℹ️ New user records were created."
                if errors:
                    response += "\n\n⚠️ Some identifiers could not be resolved:\n" + "\n".join(errors)
                response = self._append_uninviteable_warning(response, valid_user_ids)
                
                return response
            else:
                return "❌ Failed to update default users"
        except Exception as e:
            logger.error(f"Error adding to default users: {e}")
            return f"❌ Error adding to default users: {str(e)}"
    
    async def handle_remove_from_default_users(self, chat_id: int, user_ids: List) -> str:
        """Remove users from default users list (Admin only)"""
        is_admin, error = self.verify_access(chat_id)
        if not is_admin:
            return error
        
        try:
            if not user_ids:
                return "❌ Please provide at least one user ID or username.\n\nUsage: `/admin_remove_users <id_or_username1> <id_or_username2> ...`"
            
            current_users = get_default_group_users()
            resolved_user_ids, _, errors = await self._resolve_user_identifiers(user_ids)
            
            # Find users to remove
            users_to_remove = [uid for uid in resolved_user_ids if uid in current_users]
            
            if not users_to_remove:
                not_in_list = [uid for uid in resolved_user_ids if uid not in current_users]
                response = f"ℹ️ These users are not in the default list: {not_in_list}"
                if errors:
                    response += "\n\n⚠️ Some identifiers could not be resolved:\n" + "\n".join(errors)
                return response
            
            # Remove users
            updated_users = [uid for uid in current_users if uid not in users_to_remove]
            if set_default_group_users(updated_users):
                user_list = []
                for user_id in users_to_remove:
                    user = self.user_service.get_user_by_id(user_id)
                    if user:
                        user_list.append(f"  • {user.username} (ID: {user_id})")
                    else:
                        user_list.append(f"  • Unknown User (ID: {user_id})")
                
                response = "✅ Users removed from default list:\n" + "\n".join(user_list)
                if errors:
                    response += "\n\n⚠️ Some identifiers could not be resolved:\n" + "\n".join(errors)
                return response
            else:
                return "❌ Failed to update default users"
        except Exception as e:
            logger.error(f"Error removing from default users: {e}")
            return f"❌ Error removing from default users: {str(e)}"
    
    async def handle_add_user_to_db(self, chat_id: int, username: str) -> str:
        """Add new user to database (Admin only)"""
        is_admin, error = self.verify_access(chat_id)
        if not is_admin:
            return error
        
        try:
            if not username or len(username.strip()) == 0:
                return "❌ Please provide a username.\n\nUsage: `/admin_add_user <username>`"
            
            user_id, user, created = await self._resolve_user_identifier(username)
            action = "added" if created else "updated"
            return f"✅ User @{user.username or username.lstrip('@')} {action} successfully (ID: {user_id})"
        except Exception as e:
            logger.error(f"Error adding user {username}: {e}")
            return f"❌ Error adding user: {str(e)}"

    async def handle_add_user_entity(self, chat_id: int, entity, add_to_defaults: bool = False) -> str:
        """Add a Telegram entity exposed by a forwarded user message."""
        is_admin, error = self.verify_access(chat_id)
        if not is_admin:
            return error

        try:
            user_id, user, created = self._save_user_entity(entity)
            action = "added" if created else "updated"
            user_label = f"@{user.username}" if user.username else user.name
            response = f"✅ User {user_label} {action} successfully (ID: {user_id})."

            if add_to_defaults:
                current_users = get_default_group_users()
                if user_id not in current_users:
                    if set_default_group_users(current_users + [user_id]):
                        response += "\n✅ User added to default group users."
                    else:
                        response += "\n❌ Failed to add user to default group users."
                else:
                    response += "\nℹ️ User is already in default group users."

            response = self._append_uninviteable_warning(response, [user_id])
            return response
        except Exception as e:
            logger.error(f"Error adding forwarded user entity: {e}")
            return f"❌ Error adding forwarded user: {str(e)}"
    
    async def handle_get_qr_backup(self, chat_id: int) -> str:
        """Retrieve current QR backup data (Admin only)"""
        is_admin, error = self.verify_access(chat_id)
        if not is_admin:
            return error
        
        try:
            qr_data = get_qr_data()
            if qr_data:
                return f"📊 Current QR Backup Data:\n`{qr_data}`"
            else:
                return "📋 No QR backup data configured yet.\n\nUse `/admin_set_qr <qr_payload>` to configure it."
        except Exception as e:
            logger.error(f"Error getting QR backup: {e}")
            return f"❌ Error retrieving QR backup: {str(e)}"
    
    def _store_qr_backup_payload(self, qr_data: str) -> tuple:
        payload = normalize_qr_payload(qr_data)
        if not payload:
            return False, "❌ QR backup data cannot be empty.\n\nUsage: `/admin_set_qr <qr_payload>`", None

        if set_qr_backup_data(payload):
            return True, f"✅ QR backup data updated successfully!\n\nData: `{payload}`", payload
        return False, "❌ Failed to save QR backup data", None

    async def handle_set_qr_backup(self, chat_id: int, qr_data: str) -> str:
        """Set QR backup data (Admin only)"""
        is_admin, error = self.verify_access(chat_id)
        if not is_admin:
            return error
        
        try:
            _, message, _ = self._store_qr_backup_payload(qr_data)
            return message
        except Exception as e:
            logger.error(f"Error setting QR backup: {e}")
            return f"❌ Error setting QR backup: {str(e)}"

    async def handle_set_qr_backup_from_image(self, chat_id: int, image_bytes: bytes) -> str:
        """Decode and store QR backup data from a forwarded GroupHelp QR image."""
        is_admin, error = self.verify_access(chat_id)
        if not is_admin:
            return error

        try:
            payload = decode_qr_image_payload(image_bytes)
            saved, message, _ = self._store_qr_backup_payload(payload)
            if saved:
                return message.replace(
                    "QR backup data updated successfully",
                    "QR backup image decoded and stored successfully",
                    1,
                )
            return message
        except Exception as e:
            logger.error(f"Error decoding QR backup image: {e}")
            return f"❌ Error decoding QR backup image: {str(e)}"
    
    async def handle_admin_help(self, chat_id: int) -> str:
        """Show admin command help (Admin only)"""
        is_admin, error = self.verify_access(chat_id)
        if not is_admin:
            return error
        
        return """🔐 Admin Configuration Commands:

**Default Group Users Management:**
• `/admin_set_users <id_or_username> ...` - Replace entire default users list
• `/admin_add_users <id_or_username> ...` - Add users to default list
• `/admin_add_users` - Wait for a forwarded user message and add it to defaults
• `/admin_remove_users <id_or_username> ...` - Remove users from default list
• `/admin_get_users` - Show current default users
• `/admin_add_user <username>` - Resolve and save a user in the database
• `/admin_add_user` - Wait for a forwarded user message and save it

**QR Code Backup:**
• `/admin_get_qr` - Get current QR backup data
• `/admin_set_qr <qr_payload>` - Set GroupHelp backup payload rendered as a QR image
• `/admin_set_qr` - Wait for a forwarded `.importbackup` QR image and decode it

**Notes:**
✓ All admin commands work ONLY from the admin chat
✓ Users will be automatically added to new groups
✓ QR backup data is sent as a QR image with GroupHelp `.importbackup`
✓ All config changes are stored in MongoDB"""
