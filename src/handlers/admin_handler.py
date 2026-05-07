import logging
from typing import List
from src.config import (
    get_default_group_users, set_default_group_users, get_qr_data, 
    set_qr_backup_data, verify_admin_access, save_user_admin_role
)
from src.services.user_service import UserService
from src.models.user import User

logger = logging.getLogger(__name__)

class AdminHandler:
    """Handler class for admin configuration commands"""
    
    def __init__(self, user_service: UserService):
        self.user_service = user_service
    
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
                return "📋 No default users configured yet.\n\nUse `/admin_set_users <user_id1> <user_id2> ...` to configure them."
            
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
    
    async def handle_set_default_users(self, chat_id: int, user_ids: List[int]) -> str:
        """Set default users for new groups (Admin only)"""
        is_admin, error = self.verify_access(chat_id)
        if not is_admin:
            return error
        
        try:
            if not user_ids:
                return "❌ Please provide at least one user ID.\n\nUsage: `/admin_set_users <user_id1> <user_id2> ...`"
            
            # Verify all users exist
            valid_user_ids = []
            invalid_user_ids = []
            
            for user_id in user_ids:
                user = self.user_service.get_user_by_id(user_id)
                if user:
                    valid_user_ids.append(user_id)
                else:
                    invalid_user_ids.append(user_id)
            
            if not valid_user_ids:
                return f"❌ No valid users found. User IDs {invalid_user_ids} do not exist in database."
            
            # Set default users
            if set_default_group_users(valid_user_ids):
                user_list = []
                for user_id in valid_user_ids:
                    user = self.user_service.get_user_by_id(user_id)
                    if user:
                        user_list.append(f"  • {user.username} (ID: {user_id})")
                
                response = "✅ Default users updated successfully:\n" + "\n".join(user_list)
                
                if invalid_user_ids:
                    response += f"\n\n⚠️ These users were not found: {invalid_user_ids}"
                
                return response
            else:
                return "❌ Failed to save default users configuration"
        except Exception as e:
            logger.error(f"Error setting default users: {e}")
            return f"❌ Error setting default users: {str(e)}"
    
    async def handle_add_to_default_users(self, chat_id: int, user_ids: List[int]) -> str:
        """Add users to existing default users list (Admin only)"""
        is_admin, error = self.verify_access(chat_id)
        if not is_admin:
            return error
        
        try:
            if not user_ids:
                return "❌ Please provide at least one user ID.\n\nUsage: `/admin_add_users <user_id1> <user_id2> ...`"
            
            current_users = get_default_group_users()
            
            # Verify all new users exist
            valid_user_ids = []
            invalid_user_ids = []
            
            for user_id in user_ids:
                if user_id not in current_users:
                    user = self.user_service.get_user_by_id(user_id)
                    if user:
                        valid_user_ids.append(user_id)
                    else:
                        invalid_user_ids.append(user_id)
            
            if not valid_user_ids:
                if invalid_user_ids:
                    return f"❌ No valid users found. User IDs {invalid_user_ids} do not exist in database."
                else:
                    return "ℹ️ All provided users are already in the default list."
            
            # Add to default users
            updated_users = current_users + valid_user_ids
            if set_default_group_users(updated_users):
                user_list = []
                for user_id in valid_user_ids:
                    user = self.user_service.get_user_by_id(user_id)
                    if user:
                        user_list.append(f"  • {user.username} (ID: {user_id})")
                
                response = "✅ Users added to default list:\n" + "\n".join(user_list)
                
                if invalid_user_ids:
                    response += f"\n\n⚠️ These users were not found: {invalid_user_ids}"
                
                return response
            else:
                return "❌ Failed to update default users"
        except Exception as e:
            logger.error(f"Error adding to default users: {e}")
            return f"❌ Error adding to default users: {str(e)}"
    
    async def handle_remove_from_default_users(self, chat_id: int, user_ids: List[int]) -> str:
        """Remove users from default users list (Admin only)"""
        is_admin, error = self.verify_access(chat_id)
        if not is_admin:
            return error
        
        try:
            if not user_ids:
                return "❌ Please provide at least one user ID.\n\nUsage: `/admin_remove_users <user_id1> <user_id2> ...`"
            
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
    
    async def handle_add_user_to_db(self, chat_id: int, username: str) -> str:
        """Add new user to database (Admin only)"""
        is_admin, error = self.verify_access(chat_id)
        if not is_admin:
            return error
        
        try:
            if not username or len(username.strip()) == 0:
                return "❌ Please provide a username.\n\nUsage: `/admin_add_user <username>`"
            
            username = username.strip()
            
            # Generate user_id as a hash of the username
            import hashlib
            user_id = int(hashlib.md5(username.encode()).hexdigest()[:8], 16)
            
            user = User(id=user_id, username=username, name=username)
            success = self.user_service.save_user(user)
            if success:
                return f"✅ User {username} added successfully (ID: {user_id})"
            else:
                return "❌ Failed to add user"
        except Exception as e:
            logger.error(f"Error adding user {username}: {e}")
            return f"❌ Error adding user: {str(e)}"
    
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
                return "📋 No QR backup data configured yet.\n\nUse `/admin_set_qr <qr_code>` to configure it."
        except Exception as e:
            logger.error(f"Error getting QR backup: {e}")
            return f"❌ Error retrieving QR backup: {str(e)}"
    
    async def handle_set_qr_backup(self, chat_id: int, qr_data: str) -> str:
        """Set QR backup data (Admin only)"""
        is_admin, error = self.verify_access(chat_id)
        if not is_admin:
            return error
        
        try:
            if not qr_data or len(qr_data.strip()) == 0:
                return "❌ QR backup data cannot be empty.\n\nUsage: `/admin_set_qr <qr_code>`"
            
            if set_qr_backup_data(qr_data):
                return f"✅ QR backup data updated successfully!\n\nData: `{qr_data}`"
            else:
                return "❌ Failed to save QR backup data"
        except Exception as e:
            logger.error(f"Error setting QR backup: {e}")
            return f"❌ Error setting QR backup: {str(e)}"
    
    async def handle_admin_help(self, chat_id: int) -> str:
        """Show admin command help (Admin only)"""
        is_admin, error = self.verify_access(chat_id)
        if not is_admin:
            return error
        
        return """🔐 Admin Configuration Commands:

**Default Group Users Management:**
• `/admin_set_users <id1> <id2> ...` - Replace entire default users list
• `/admin_add_users <id1> <id2> ...` - Add users to default list
• `/admin_remove_users <id1> <id2> ...` - Remove users from default list
• `/admin_get_users` - Show current default users
• `/admin_add_user <username>` - Add new user to database

**QR Code Backup:**
• `/admin_get_qr` - Get current QR backup data
• `/admin_set_qr <qr_code>` - Set QR backup data

**Notes:**
✓ All admin commands work ONLY from the admin chat
✓ Users will be automatically added to new groups
✓ QR backup data is used for session replication
✓ All config changes are stored in MongoDB"""
