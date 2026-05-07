import logging
from typing import List, Optional
from src.models.user import User
from src.services.mongodb_service import MongoDBService

logger = logging.getLogger(__name__)

class UserService:
    """Service class for user management operations"""
    
    def __init__(self, mongo_service: MongoDBService):
        self.mongo_service = mongo_service
    
    def get_all_users(self) -> List[User]:
        """Retrieve all users from MongoDB"""
        return self.mongo_service.get_users()
    
    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Retrieve a specific user by ID from MongoDB"""
        return self.mongo_service.get_user_by_id(user_id)
    
    def save_user(self, user: User) -> bool:
        """Save a user to MongoDB"""
        return self.mongo_service.save_user(user)
    
    def delete_user(self, user_id: int) -> bool:
        """Delete a user from MongoDB"""
        return self.mongo_service.delete_user(user_id)
    
    def update_user(self, user: User) -> bool:
        """Update an existing user in MongoDB"""
        return self.mongo_service.save_user(user)
    
    def get_users_by_role(self, role: str) -> List[User]:
        """Retrieve users by role from MongoDB"""
        try:
            users = self.get_all_users()
            return [user for user in users if user.role == role]
        except Exception as e:
            logger.error(f"Error retrieving users by role '{role}': {e}")
            return []
    
    def get_active_users(self) -> List[User]:
        """Retrieve all active users from MongoDB"""
        try:
            users = self.get_all_users()
            return [user for user in users if user.is_active]
        except Exception as e:
            logger.error(f"Error retrieving active users: {e}")
            return []