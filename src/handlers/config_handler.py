import logging
from typing import List
from src.config import get_default_group_users, set_default_group_users, get_qr_data, set_qr_backup_data
from src.models.user import User
from src.services.user_service import UserService

logger = logging.getLogger(__name__)

class ConfigHandler:
    """Handler class for configuration-related commands"""
    
    def __init__(self, user_service: UserService):
        self.user_service = user_service

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
        created_note = " (placeholder created)" if created else ""
        username = f"@{user.username}" if user.username else user.name
        return f"  • {username} (ID: {user_id}){created_note}"
    
    async def handle_get_default_users(self) -> str:
        """Get current default users for new groups"""
        try:
            default_users = get_default_group_users()
            if not default_users:
                return "📋 No default users configured yet.\n\nUse `/set_default_users <user_id1> <user_id2> ...` to configure them."
            
            user_list = []
            for user_id in default_users:
                user = self.user_service.get_user_by_id(user_id)
                if user:
                    user_list.append(f"  • {user.username} (ID: {user_id})")
                else:
                    user_list.append(f"  • Unknown User (ID: {user_id})")
            
            return "📋 Current default users for new groups:\n" + "\n".join(user_list)
        except Exception as e:
            logger.error(f"Error getting default users: {e}")
            return f"❌ Error retrieving default users: {str(e)}"
    
    async def handle_set_default_users(self, user_ids: List[int]) -> str:
        """Set default users for new groups"""
        try:
            if not user_ids:
                return "❌ Please provide at least one user ID.\n\nUsage: `/set_default_users <user_id1> <user_id2> ...`"
            
            valid_user_ids = []
            created_users = []
            
            for user_id in user_ids:
                _, created = self._ensure_user_record(user_id)
                valid_user_ids.append(user_id)
                if created:
                    created_users.append(user_id)
            
            # Set default users
            if set_default_group_users(valid_user_ids):
                user_list = []
                for user_id in valid_user_ids:
                    user = self.user_service.get_user_by_id(user_id)
                    if user:
                        user_list.append(self._format_user(user, user_id, user_id in created_users))
                
                response = "✅ Default users updated successfully:\n" + "\n".join(user_list)
                if created_users:
                    response += "\n\nℹ️ Placeholder records were created for new Telegram IDs."
                
                return response
            else:
                return "❌ Failed to save default users configuration"
        except Exception as e:
            logger.error(f"Error setting default users: {e}")
            return f"❌ Error setting default users: {str(e)}"
    
    async def handle_add_to_default_users(self, user_ids: List[int]) -> str:
        """Add users to existing default users list"""
        try:
            if not user_ids:
                return "❌ Please provide at least one user ID.\n\nUsage: `/add_default_users <user_id1> <user_id2> ...`"
            
            current_users = get_default_group_users()
            
            valid_user_ids = []
            created_users = []
            
            for user_id in user_ids:
                if user_id not in current_users:
                    _, created = self._ensure_user_record(user_id)
                    valid_user_ids.append(user_id)
                    if created:
                        created_users.append(user_id)
            
            if not valid_user_ids:
                return "ℹ️ All provided users are already in the default list."
            
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
                    response += "\n\nℹ️ Placeholder records were created for new Telegram IDs."
                
                return response
            else:
                return "❌ Failed to update default users"
        except Exception as e:
            logger.error(f"Error adding to default users: {e}")
            return f"❌ Error adding to default users: {str(e)}"
    
    async def handle_remove_from_default_users(self, user_ids: List[int]) -> str:
        """Remove users from default users list"""
        try:
            if not user_ids:
                return "❌ Please provide at least one user ID.\n\nUsage: `/remove_default_users <user_id1> <user_id2> ...`"
            
            current_users = get_default_group_users()
            
            # Find users to remove
            users_to_remove = [uid for uid in user_ids if uid in current_users]
            
            if not users_to_remove:
                not_in_list = [uid for uid in user_ids if uid not in current_users]
                return f"ℹ️ These users are not in the default list: {not_in_list}"
            
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
                
                return "✅ Users removed from default list:\n" + "\n".join(user_list)
            else:
                return "❌ Failed to update default users"
        except Exception as e:
            logger.error(f"Error removing from default users: {e}")
            return f"❌ Error removing from default users: {str(e)}"
    
    async def handle_get_qr_backup(self) -> str:
        """Retrieve current QR backup data"""
        try:
            qr_data = get_qr_data()
            if qr_data:
                return f"📊 Current QR Backup Data:\n`{qr_data}`"
            else:
                return "📋 No QR backup data configured yet.\n\nUse `/set_qr_backup <qr_payload>` to configure it."
        except Exception as e:
            logger.error(f"Error getting QR backup: {e}")
            return f"❌ Error retrieving QR backup: {str(e)}"
    
    async def handle_set_qr_backup(self, qr_data: str) -> str:
        """Set QR backup data"""
        try:
            if not qr_data or len(qr_data.strip()) == 0:
                return "❌ QR backup data cannot be empty.\n\nUsage: `/set_qr_backup <qr_payload>`"
            
            if set_qr_backup_data(qr_data):
                return f"✅ QR backup data updated successfully!\n\nData: `{qr_data}`"
            else:
                return "❌ Failed to save QR backup data"
        except Exception as e:
            logger.error(f"Error setting QR backup: {e}")
            return f"❌ Error setting QR backup: {str(e)}"
    
    async def handle_help_config(self) -> str:
        """Show configuration command help"""
        return """📖 Configuration Commands:

**Default Group Users:**
• `/get_default_users` - Show current default users
• `/set_default_users <user_id1> <user_id2> ...` - Set default users
• `/add_default_users <user_id1> <user_id2> ...` - Add users to default list
• `/remove_default_users <user_id1> <user_id2> ...` - Remove users from default list

**QR Code Backup:**
• `/get_qr_backup` - Get current QR backup data
• `/set_qr_backup <qr_payload>` - Set GroupHelp backup payload rendered as a QR image for `.importbackup`

When a new group is created without specifying users, all configured default users will be automatically added."""
