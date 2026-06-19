import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from telethon import TelegramClient
from telethon.sessions import StringSession

# Telegram configuration
TELETHON_TOKEN = os.environ.get("TELETHON_TOKEN")
TELETHON_API_HASH = os.environ.get("TELETHON_API_HASH")
TELETHON_API_ID = int(os.environ.get("TELETHON_API_ID", 0))
STAFF_CHAT_ID = int(os.environ.get("STAFF_CHAT_ID", 0))
FACTORY_BOT_ID = int(os.environ.get("FACTORY_BOT_ID") or 0)
FACTORY_BOT_USERNAME = os.environ.get("FACTORY_BOT_USERNAME", "").strip()

# MongoDB configuration
MONGODB_URI = os.environ.get('MONGODB_URI', '')
MONGODB_DATABASE = os.environ.get('MONGODB_DATABASE', '')
MONGODB_COLLECTION = os.environ.get('MONGODB_COLLECTION', '')

# Logging configuration
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

def get_telegram_session():
    """Return a Telethon session backed by TELETHON_TOKEN when configured."""
    if TELETHON_TOKEN:
        return StringSession(TELETHON_TOKEN)
    return 'session'

# MongoDB helper functions
def get_mongo_client():
    """Create and return MongoDB client"""
    try:
        client = MongoClient(MONGODB_URI)
        client.admin.command('ping')
        return client
    except ConnectionFailure as e:
        print(f"MongoDB connection failed: {e}")
        return None

def get_telegram_client():
    """Create and return Telegram client"""
    try:
        client = TelegramClient(
            get_telegram_session(),
            TELETHON_API_ID,
            TELETHON_API_HASH
        )
        return client
    except Exception as e:
        print(f"Telegram client creation failed: {e}")
        return None

def get_qr_data():
    """Retrieve QR data string from MongoDB ghconfig collection"""
    try:
        client = get_mongo_client()
        if client:
            db = client[MONGODB_DATABASE]
            collection = db[MONGODB_COLLECTION]
            result = collection.find_one({'key': 'qr_backup_data'})
            client.close()
            if result and 'value' in result:
                return result['value']
        return None
    except Exception as e:
        print(f"Failed to retrieve QR data: {e}")
        return None

def load_config():
    """Load configuration from environment variables"""
    return {
        'telegram': {
            'api_id': TELETHON_API_ID,
            'api_hash': TELETHON_API_HASH,
            'session': get_telegram_session(),
            'session_file': 'session',
            'staff_chat_id': STAFF_CHAT_ID,
            'factory_bot_id': FACTORY_BOT_ID,
            'factory_bot_username': FACTORY_BOT_USERNAME,
        },
        'mongodb': {
            'uri': MONGODB_URI,
            'database': MONGODB_DATABASE,
            'collection': MONGODB_COLLECTION
        },
        'logging': {
            'level': LOG_LEVEL
        }
    }

def get_default_group_users():
    """Retrieve default users to add to new groups from MongoDB"""
    try:
        client = get_mongo_client()
        if client:
            db = client[MONGODB_DATABASE]
            config_collection = db['group_config']
            result = config_collection.find_one({'key': 'default_users'})
            client.close()
            if result and 'value' in result:
                return result['value']  # Should be a list of user IDs
        return []
    except Exception as e:
        print(f"Failed to retrieve default group users: {e}")
        return []

def set_default_group_users(user_ids: list):
    """Store default users to add to new groups in MongoDB"""
    try:
        client = get_mongo_client()
        if client:
            db = client[MONGODB_DATABASE]
            config_collection = db['group_config']
            config_collection.update_one(
                {'key': 'default_users'},
                {'$set': {'value': user_ids}},
                upsert=True
            )
            client.close()
            return True
        return False
    except Exception as e:
        print(f"Failed to set default group users: {e}")
        return False

def set_qr_backup_data(qr_data: str):
    """Store backup QR code data in MongoDB"""
    try:
        client = get_mongo_client()
        if client:
            db = client[MONGODB_DATABASE]
            collection = db[MONGODB_COLLECTION]
            collection.update_one(
                {'key': 'qr_backup_data'},
                {'$set': {'value': qr_data}},
                upsert=True
            )
            client.close()
            return True
        return False
    except Exception as e:
        print(f"Failed to set QR backup data: {e}")
        return False

def is_admin_chat(chat_id: int) -> bool:
    """Verify if the message came from the admin chat"""
    return chat_id == STAFF_CHAT_ID

def verify_admin_access(chat_id: int) -> tuple:
    """Verify admin access and return (is_admin, message)"""
    if is_admin_chat(chat_id):
        return True, None
    else:
        return False, f"❌ Admin commands can only be executed in the admin chat (ID: {STAFF_CHAT_ID})"

def save_user_admin_role(user_id: int, is_full_admin: bool):
    """Save whether user wants to be a full admin when joining groups"""
    try:
        client = get_mongo_client()
        if client:
            db = client[MONGODB_DATABASE]
            admin_collection = db['user_admin_roles']
            admin_collection.update_one(
                {'user_id': user_id},
                {'$set': {'is_full_admin': is_full_admin}},
                upsert=True
            )
            client.close()
            return True
        return False
    except Exception as e:
        print(f"Failed to save user admin role: {e}")
        return False

def get_user_admin_role(user_id: int) -> bool:
    """Get whether user wants to be a full admin when joining groups"""
    try:
        client = get_mongo_client()
        if client:
            db = client[MONGODB_DATABASE]
            admin_collection = db['user_admin_roles']
            result = admin_collection.find_one({'user_id': user_id})
            client.close()
            if result:
                return result.get('is_full_admin', False)
        return False
    except Exception as e:
        print(f"Failed to get user admin role: {e}")
        return False
