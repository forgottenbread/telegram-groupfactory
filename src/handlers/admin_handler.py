import logging
import re
from typing import List
from src.config import (
    get_default_group_users, set_default_group_users, get_qr_data, 
    set_qr_backup_data, verify_admin_access, DEFAULT_QR_GROUP,
    normalize_qr_group_name, list_qr_groups, get_qr_group_assignments,
    normalize_telegram_group_id, set_qr_group_assignment,
    remove_qr_group_assignment
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

    def _parse_id_username_pair(self, identifier: str):
        match = re.fullmatch(r"(-?\d+)\s*[:=,|]\s*@?([A-Za-z0-9_]{5,32})", identifier)
        if not match:
            return None
        return int(match.group(1)), match.group(2)

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

        id_username_pair = self._parse_id_username_pair(identifier)
        if id_username_pair:
            provided_user_id, provided_username = id_username_pair
            existing = self.user_service.get_user_by_id(provided_user_id)
            created = existing is None

            user = User(
                id=provided_user_id,
                username=provided_username,
                first_name=existing.first_name if existing else None,
                last_name=existing.last_name if existing else None,
                access_hash=existing.access_hash if existing else None,
            )

            if self.telegram_client:
                try:
                    entity = await self.telegram_client.get_entity(provided_username)
                except Exception as e:
                    logger.info(
                        "Could not resolve username @%s while storing ID pair %s: %s",
                        provided_username,
                        provided_user_id,
                        e,
                    )
                else:
                    if entity.id != provided_user_id:
                        raise ValueError(
                            f"@{provided_username} resolves to Telegram ID {entity.id}, not {provided_user_id}"
                        )
                    user = self._user_from_entity(entity, fallback_username=provided_username)

            if not self.user_service.save_user(user):
                raise RuntimeError(f"Failed to save user {provided_user_id}")
            return provided_user_id, user, created

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

    def _qr_group_label(self, group_name: str = None) -> str:
        return normalize_qr_group_name(group_name or DEFAULT_QR_GROUP)
    
    async def handle_get_default_users(self, chat_id: int) -> str:
        """Get current default users for new groups (Admin only)"""
        is_admin, error = self.verify_access(chat_id)
        if not is_admin:
            return error
        
        try:
            default_users = get_default_group_users()
            if not default_users:
                return "📋 No default users configured yet.\n\nUse `/admin_set_users <id_or_username_or_id:username> ...` to configure them."
            
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
                return "❌ Please provide at least one user ID, username, or id:username pair.\n\nUsage: `/admin_set_users <id_or_username_or_id:username> ...`"
            
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
                return "❌ Please provide at least one user ID, username, or id:username pair.\n\nUsage: `/admin_add_users <id_or_username_or_id:username> ...`"
            
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
                return "❌ Please provide at least one user ID, username, or id:username pair.\n\nUsage: `/admin_remove_users <id_or_username_or_id:username> ...`"
            
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
                return "❌ Please provide a username or id:username pair.\n\nUsage: `/admin_add_user <username_or_id:username>`"
            
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
    
    async def handle_get_qr_backup(self, chat_id: int, qr_group: str = None) -> str:
        """Retrieve current QR backup data (Admin only)"""
        is_admin, error = self.verify_access(chat_id)
        if not is_admin:
            return error
        
        try:
            group = self._qr_group_label(qr_group)
            qr_data = get_qr_data(group)
            if qr_data:
                return f"📊 Current QR Backup Data for `{group}`:\n`{qr_data}`"
            else:
                return f"📋 No QR backup data configured for `{group}`.\n\nUse `/admin_set_qr {group} <qr_payload>` to configure it."
        except Exception as e:
            logger.error(f"Error getting QR backup: {e}")
            return f"❌ Error retrieving QR backup: {str(e)}"
    
    def _store_qr_backup_payload(self, qr_data: str, qr_group: str = None) -> tuple:
        group = self._qr_group_label(qr_group)
        payload = normalize_qr_payload(qr_data)
        if not payload:
            return False, "❌ QR backup data cannot be empty.\n\nUsage: `/admin_set_qr [qr_group] <qr_payload>`", None

        if set_qr_backup_data(payload, group):
            return True, f"✅ QR backup data for `{group}` updated successfully!\n\nData: `{payload}`", payload
        return False, "❌ Failed to save QR backup data", None

    async def handle_set_qr_backup(self, chat_id: int, qr_data: str, qr_group: str = None) -> str:
        """Set QR backup data (Admin only)"""
        is_admin, error = self.verify_access(chat_id)
        if not is_admin:
            return error
        
        try:
            _, message, _ = self._store_qr_backup_payload(qr_data, qr_group)
            return message
        except Exception as e:
            logger.error(f"Error setting QR backup: {e}")
            return f"❌ Error setting QR backup: {str(e)}"

    async def handle_set_qr_backup_from_image(self, chat_id: int, image_bytes: bytes, qr_group: str = None) -> str:
        """Decode and store QR backup data from a forwarded GroupHelp QR image."""
        is_admin, error = self.verify_access(chat_id)
        if not is_admin:
            return error

        try:
            group = self._qr_group_label(qr_group)
            payload = decode_qr_image_payload(image_bytes)
            saved, message, _ = self._store_qr_backup_payload(payload, group)
            if saved:
                return message.replace(
                    f"QR backup data for `{group}` updated successfully",
                    f"QR backup image for `{group}` decoded and stored successfully",
                    1,
                )
            return message
        except Exception as e:
            logger.error(f"Error decoding QR backup image: {e}")
            return f"❌ Error decoding QR backup image: {str(e)}"

    async def handle_assign_qr_group(self, chat_id: int, qr_group: str, group_ids: List[str]) -> str:
        """Assign Telegram groups to a logical QR config group."""
        is_admin, error = self.verify_access(chat_id)
        if not is_admin:
            return error

        try:
            group = self._qr_group_label(qr_group)
            if not group_ids:
                return "❌ Please provide at least one Telegram group ID.\n\nUsage: `/admin_qr_group_add <qr_group> <telegram_group_id> ...`"

            assigned = []
            failed = []
            invalid = []
            for raw_group_id in group_ids:
                try:
                    group_id = normalize_telegram_group_id(raw_group_id)
                except ValueError:
                    invalid.append(str(raw_group_id))
                    continue

                if set_qr_group_assignment(group, group_id):
                    assigned.append(group_id)
                else:
                    failed.append(group_id)

            response = f"✅ QR group `{group}` assignments updated."
            if assigned:
                response += "\nAssigned groups:\n" + "\n".join([f"  • {item}" for item in assigned])
            if failed:
                response += "\n\n❌ Failed assignments:\n" + "\n".join([f"  • {item}" for item in failed])
            if invalid:
                response += "\n\n⚠️ Invalid group IDs:\n" + "\n".join([f"  • {item}" for item in invalid])
            if not get_qr_data(group):
                response += f"\n\n⚠️ No QR payload is configured for `{group}` yet."
            return response
        except Exception as e:
            logger.error(f"Error assigning QR group {qr_group}: {e}")
            return f"❌ Error assigning QR group: {str(e)}"

    async def handle_remove_qr_group_assignment(self, chat_id: int, group_ids: List[str]) -> str:
        """Remove Telegram group logical QR assignments."""
        is_admin, error = self.verify_access(chat_id)
        if not is_admin:
            return error

        try:
            if not group_ids:
                return "❌ Please provide at least one Telegram group ID.\n\nUsage: `/admin_qr_group_remove <telegram_group_id> ...`"

            removed = []
            missing = []
            invalid = []
            for raw_group_id in group_ids:
                try:
                    group_id = normalize_telegram_group_id(raw_group_id)
                except ValueError:
                    invalid.append(str(raw_group_id))
                    continue

                if remove_qr_group_assignment(group_id):
                    removed.append(group_id)
                else:
                    missing.append(group_id)

            response = "✅ QR group assignments updated."
            if removed:
                response += "\nRemoved assignments:\n" + "\n".join([f"  • {item}" for item in removed])
            if missing:
                response += "\n\nℹ️ No assignment existed for:\n" + "\n".join([f"  • {item}" for item in missing])
            if invalid:
                response += "\n\n⚠️ Invalid group IDs:\n" + "\n".join([f"  • {item}" for item in invalid])
            return response
        except Exception as e:
            logger.error(f"Error removing QR group assignments: {e}")
            return f"❌ Error removing QR group assignments: {str(e)}"

    async def handle_list_qr_groups(self, chat_id: int, qr_group: str = None) -> str:
        """List logical QR config groups and Telegram group assignments."""
        is_admin, error = self.verify_access(chat_id)
        if not is_admin:
            return error

        try:
            target_group = self._qr_group_label(qr_group) if qr_group else None
            groups = [target_group] if target_group else list_qr_groups(include_assignments=True)
            if DEFAULT_QR_GROUP not in groups and not target_group:
                groups.insert(0, DEFAULT_QR_GROUP)

            assignments = get_qr_group_assignments(target_group)
            lines = []
            for group in groups:
                qr_status = "configured" if get_qr_data(group) else "missing QR"
                group_assignments = {
                    group_id: item for group_id, item in assignments.items()
                    if item.get('group') == group
                }
                lines.append(f"• `{group}` - {qr_status} - {len(group_assignments)} assigned groups")
                for group_id, item in sorted(group_assignments.items()):
                    title = item.get('title')
                    suffix = f" ({title})" if title else ""
                    lines.append(f"  - {group_id}{suffix}")

            if not lines:
                return "📋 No QR groups configured yet."
            return "📋 QR config groups:\n" + "\n".join(lines)
        except Exception as e:
            logger.error(f"Error listing QR groups: {e}")
            return f"❌ Error listing QR groups: {str(e)}"
    
    async def handle_admin_help(self, chat_id: int) -> str:
        """Show admin command help (Admin only)"""
        is_admin, error = self.verify_access(chat_id)
        if not is_admin:
            return error
        
        return """🔐 Admin Configuration Commands:

**Default Group Users Management:**
• `/admin_set_users <id_or_username_or_id:username> ...` - Replace entire default users list
• `/admin_add_users <id_or_username_or_id:username> ...` - Add users to default list
• `/admin_add_users` - Wait for a forwarded user message and add it to defaults
• `/admin_remove_users <id_or_username_or_id:username> ...` - Remove users from default list
• `/admin_get_users` - Show current default users
• `/admin_add_user <username_or_id:username>` - Resolve and save a user in the database
• `/admin_add_user` - Wait for a forwarded user message and save it

**QR Code Backup:**
• `/admin_get_qr [qr_group]` - Get QR backup data
• `/admin_set_qr [qr_group] <qr_payload>` - Set GroupHelp backup payload
• `/admin_set_qr` - Wait for a forwarded `.importbackup` QR image for `default`
• `/admin_set_qr_group <qr_group>` - Wait for a forwarded `.importbackup` QR image for a QR group
• `/admin_qr_groups [qr_group]` - List QR config groups and assignments
• `/admin_qr_group_add <qr_group> <telegram_group_id> ...` - Assign groups to a QR config
• `/admin_qr_group_remove <telegram_group_id> ...` - Remove QR config assignments
• `/admin_sync_qr [qr_group|all]` - Send stored `.importbackup` QR to owned assigned groups

**Notes:**
✓ All admin commands work ONLY from the admin chat
✓ Users will be automatically added to new groups
✓ QR backup data is sent as a QR image with GroupHelp `.importbackup`
✓ All config changes are stored in MongoDB"""
