import logging
from typing import List
from src.services.user_service import UserService
from src.models.user import User

logger = logging.getLogger(__name__)

class UserHandler:
    """Handler class for user-related commands"""
    
    def __init__(self, user_service: UserService):
        self.user_service = user_service
    
    def handle_get_all_users(self) -> str:
        """Handle command to get all users"""
        try:
            users = self.user_service.get_all_users()
            if users:
                user_list = "\n".join([f"• {user.username} ({user.name}) - ID: {user.id}" for user in users])
                return f"👥 All Users ({len(users)}):\n{user_list}"
            else:
                return "📭 No users found"
        except Exception as e:
            logger.error(f"Error retrieving users: {e}")
            return f"❌ Error retrieving users: {str(e)}"
    
    def handle_get_user_by_id(self, user_id: int) -> str:
        """Handle command to get a specific user by ID"""
        try:
            user = self.user_service.get_user_by_id(user_id)
            if user:
                return f"👤 User Info:\nID: {user.id}\nUsername: {user.username}\nName: {user.name}"
            else:
                return f"❌ User with ID {user_id} not found"
        except Exception as e:
            logger.error(f"Error retrieving user {user_id}: {e}")
            return f"❌ Error retrieving user: {str(e)}"
    
    def handle_add_user(self, username: str) -> str:
        """Handle command to add a new user"""
        try:
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
    
    def handle_delete_user(self, user_id: int) -> str:
        """Handle command to delete a user"""
        try:
            success = self.user_service.delete_user(user_id)
            if success:
                return f"✅ User with ID {user_id} deleted successfully"
            else:
                return "❌ Failed to delete user"
        except Exception as e:
            logger.error(f"Error deleting user {user_id}: {e}")
            return f"❌ Error deleting user: {str(e)}"