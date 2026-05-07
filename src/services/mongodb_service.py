import logging
from typing import List, Optional
from pymongo import MongoClient
from src.models.user import User
from src.config import get_mongo_client

logger = logging.getLogger(__name__)

class MongoDBService:
    """Service class for MongoDB operations"""
    
    def __init__(self, database_name: str, collection_name: str):
        self.database_name = database_name
        self.collection_name = collection_name
        self.client = None
        self.db = None
        self.collection = None
        self._connect()
    
    def _connect(self):
        """Establish connection to MongoDB"""
        try:
            self.client = get_mongo_client()
            if self.client:
                self.db = self.client[self.database_name]
                self.collection = self.db[self.collection_name]
                logger.info("Successfully connected to MongoDB")
            else:
                logger.error("Failed to connect to MongoDB")
        except Exception as e:
            logger.error(f"Error connecting to MongoDB: {e}")
    
    def get_users(self) -> List[User]:
        """Retrieve all users from MongoDB collection"""
        try:
            if not self.collection:
                logger.error("MongoDB collection not initialized")
                return []
            
            users_data = list(self.collection.find({'type': 'user'}))
            users = [User.from_dict(user_data) for user_data in users_data]
            logger.info(f"Retrieved {len(users)} users from MongoDB")
            return users
        except Exception as e:
            logger.error(f"Error retrieving users from MongoDB: {e}")
            return []
    
    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Retrieve a specific user by ID from MongoDB"""
        try:
            if not self.collection:
                logger.error("MongoDB collection not initialized")
                return None
            
            user_data = self.collection.find_one({'id': user_id, 'type': 'user'})
            if user_data:
                return User.from_dict(user_data)
            return None
        except Exception as e:
            logger.error(f"Error retrieving user {user_id} from MongoDB: {e}")
            return None
    
    def save_user(self, user: User) -> bool:
        """Save a user to MongoDB collection"""
        try:
            if not self.collection:
                logger.error("MongoDB collection not initialized")
                return False
            
            user_data = user.to_dict()
            user_data['type'] = 'user'
            
            result = self.collection.replace_one(
                {'id': user.id, 'type': 'user'},
                user_data,
                upsert=True
            )
            logger.info(f"Saved user {user.id} to MongoDB")
            return result.modified_count > 0 or result.upserted_id is not None
        except Exception as e:
            logger.error(f"Error saving user {user.id} to MongoDB: {e}")
            return False
    
    def delete_user(self, user_id: int) -> bool:
        """Delete a user from MongoDB collection"""
        try:
            if not self.collection:
                logger.error("MongoDB collection not initialized")
                return False
            
            result = self.collection.delete_one({'id': user_id, 'type': 'user'})
            logger.info(f"Deleted user {user_id} from MongoDB")
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Error deleting user {user_id} from MongoDB: {e}")
            return False
    
    def close(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            logger.info("Closed MongoDB connection")