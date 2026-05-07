import logging
from typing import List
from src.services.user_service import UserService
from src.services.group_service import GroupService

logger = logging.getLogger(__name__)

class GroupHandler:
    """Handler class for group-related commands"""
    
    def __init__(self, user_service: UserService, group_service: GroupService):
        self.user_service = user_service
        self.group_service = group_service
    
    async def handle_create_group(self, group_name: str, user_ids: List[int]) -> str:
        """Handle command to create a new group"""
        try:
            group_id = await self.group_service.create_group(group_name, user_ids)
            if group_id:
                return f"✅ Group '{group_name}' created successfully with ID: {group_id}"
            else:
                return "❌ Failed to create group"
        except Exception as e:
            logger.error(f"Error creating group '{group_name}': {e}")
            return f"❌ Error creating group: {str(e)}"
    
    async def handle_add_users(self, group_id: str, user_ids: List[int]) -> str:
        """Handle command to add users to a group"""
        try:
            success = await self.group_service.add_users_to_group(group_id, user_ids)
            if success:
                return f"✅ Successfully added users to group {group_id}"
            else:
                return "❌ Failed to add users to group"
        except Exception as e:
            logger.error(f"Error adding users to group {group_id}: {e}")
            return f"❌ Error adding users: {str(e)}"
    
    async def handle_get_group_info(self, group_id: str) -> str:
        """Handle command to get group information"""
        try:
            group_info = await self.group_service.get_group_info(group_id)
            if group_info:
                return f"ℹ️ Group Info:\n{group_info}"
            else:
                return "❌ Failed to retrieve group information"
        except Exception as e:
            logger.error(f"Error retrieving group info for {group_id}: {e}")
            return f"❌ Error retrieving group info: {str(e)}"