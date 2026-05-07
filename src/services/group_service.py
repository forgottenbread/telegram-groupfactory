import logging
from typing import List, Optional
from src.models.user import User
from src.services.mongodb_service import MongoDBService
from src.config import get_telegram_client, get_default_group_users

logger = logging.getLogger(__name__)

class GroupService:
    """Service class for group creation and management"""
    
    def __init__(self, mongo_service: MongoDBService):
        self.mongo_service = mongo_service
        self.client = get_telegram_client()
    
    async def create_group(self, group_name: str, user_ids: List[int] = None) -> Optional[str]:
        """Create a Telegram group with specified users or default users"""
        try:
            if not self.client:
                logger.error("Telegram client not initialized")
                return None
            
            # Use default users if none specified
            if user_ids is None or len(user_ids) == 0:
                user_ids = get_default_group_users()
                if len(user_ids) == 0:
                    logger.warning("No default users configured for group creation")
            
            # Get users from MongoDB
            users = []
            for user_id in user_ids:
                user = self.mongo_service.get_user_by_id(user_id)
                if user:
                    users.append(user)
                else:
                    logger.warning(f"User {user_id} not found in database")
            
            if not users:
                logger.warning("No valid users found for group creation")
                return None
            
            # Create group using Telegram API
            result = await self.client.create_group(group_name, [user.id for user in users])
            
            if result:
                logger.info(f"Successfully created group '{group_name}' with {len(users)} members")
                return result.id
            else:
                logger.error("Failed to create group")
                return None
                
        except Exception as e:
            logger.error(f"Error creating group '{group_name}': {e}")
            return None
    
    async def add_users_to_group(self, group_id: str, user_ids: List[int]) -> bool:
        """Add users to an existing Telegram group"""
        try:
            if not self.client:
                logger.error("Telegram client not initialized")
                return False
            
            # Get users from MongoDB
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
            
            # Add users to group using Telegram API
            result = await self.client.add_users_to_group(group_id, [user.id for user in users])
            
            if result:
                logger.info(f"Successfully added {len(users)} users to group {group_id}")
                return True
            else:
                logger.error("Failed to add users to group")
                return False
                
        except Exception as e:
            logger.error(f"Error adding users to group {group_id}: {e}")
            return False
    
    async def get_group_info(self, group_id: str) -> Optional[dict]:
        """Get information about a Telegram group"""
        try:
            if not self.client:
                logger.error("Telegram client not initialized")
                return None
            
            # Get group info using Telegram API
            result = await self.client.get_group_info(group_id)
            
            if result:
                logger.info(f"Retrieved information for group {group_id}")
                return result
            else:
                logger.warning(f"Failed to retrieve information for group {group_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error retrieving group info for {group_id}: {e}")
            return None