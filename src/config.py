import os
import re
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
DEFAULT_QR_GROUP = "default"
QR_ASSIGNMENTS_KEY = "qr_group_assignments"

def normalize_qr_group_name(group_name: str = None) -> str:
    """Normalize the logical QR config group name used in MongoDB keys."""
    group = (group_name or DEFAULT_QR_GROUP).strip().lower()
    if not group:
        group = DEFAULT_QR_GROUP
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,62}", group):
        raise ValueError("QR group names must use letters, numbers, dot, underscore, or dash")
    return group

def _qr_backup_key(group_name: str = None) -> str:
    group = normalize_qr_group_name(group_name)
    if group == DEFAULT_QR_GROUP:
        return "qr_backup_data"
    return f"qr_backup_data:{group}"

def _assignment_group(value):
    if isinstance(value, dict):
        return normalize_qr_group_name(value.get("group"))
    return normalize_qr_group_name(value)

def _assignment_title(value):
    if isinstance(value, dict):
        return value.get("title")
    return None

def normalize_telegram_group_id(telegram_group_id) -> str:
    """Normalize a Telegram group ID used as a MongoDB assignment key."""
    group_id = str(telegram_group_id).strip().rstrip(",")
    if not group_id or not group_id.lstrip("-").isdigit():
        raise ValueError("Telegram group ID must be numeric")
    return group_id

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

def get_qr_data(group_name: str = None):
    """Retrieve QR data string from MongoDB ghconfig collection."""
    try:
        key = _qr_backup_key(group_name)
        client = get_mongo_client()
        if client:
            db = client[MONGODB_DATABASE]
            collection = db[MONGODB_COLLECTION]
            result = collection.find_one({'key': key})
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

def set_qr_backup_data(qr_data: str, group_name: str = None):
    """Store backup QR code data in MongoDB."""
    try:
        group = normalize_qr_group_name(group_name)
        key = _qr_backup_key(group)
        client = get_mongo_client()
        if client:
            db = client[MONGODB_DATABASE]
            collection = db[MONGODB_COLLECTION]
            collection.update_one(
                {'key': key},
                {'$set': {'value': qr_data, 'group': group}},
                upsert=True
            )
            client.close()
            return True
        return False
    except Exception as e:
        print(f"Failed to set QR backup data: {e}")
        return False

def list_qr_groups(include_assignments: bool = True):
    """List logical QR config group names known from QR payloads and assignments."""
    groups = set()
    try:
        client = get_mongo_client()
        if client:
            db = client[MONGODB_DATABASE]
            collection = db[MONGODB_COLLECTION]
            for result in collection.find({'key': {'$regex': r'^qr_backup_data(:.*)?$'}}):
                key = result.get('key')
                if key == 'qr_backup_data':
                    groups.add(DEFAULT_QR_GROUP)
                elif key and key.startswith('qr_backup_data:'):
                    groups.add(normalize_qr_group_name(key.split(':', 1)[1]))
            if include_assignments:
                assignment_doc = collection.find_one({'key': QR_ASSIGNMENTS_KEY})
                assignments = (assignment_doc or {}).get('value') or {}
                for assignment in assignments.values():
                    groups.add(_assignment_group(assignment))
            client.close()
    except Exception as e:
        print(f"Failed to list QR groups: {e}")
    return sorted(groups)

def get_qr_group_assignments(group_name: str = None):
    """Return Telegram group-id assignments for logical QR config groups."""
    try:
        target_group = normalize_qr_group_name(group_name) if group_name else None
        client = get_mongo_client()
        if client:
            db = client[MONGODB_DATABASE]
            collection = db[MONGODB_COLLECTION]
            result = collection.find_one({'key': QR_ASSIGNMENTS_KEY})
            client.close()
            assignments = (result or {}).get('value') or {}
            normalized = {}
            for telegram_group_id, assignment in assignments.items():
                assignment_group = _assignment_group(assignment)
                if target_group and assignment_group != target_group:
                    continue
                normalized[str(telegram_group_id)] = {
                    'group': assignment_group,
                    'title': _assignment_title(assignment),
                }
            return normalized
        return {}
    except Exception as e:
        print(f"Failed to retrieve QR group assignments: {e}")
        return {}

def set_qr_group_assignment(group_name: str, telegram_group_id, title: str = None):
    """Assign a Telegram group to a logical QR config group."""
    try:
        group = normalize_qr_group_name(group_name)
        group_id = normalize_telegram_group_id(telegram_group_id)

        client = get_mongo_client()
        if client:
            db = client[MONGODB_DATABASE]
            collection = db[MONGODB_COLLECTION]
            value = {'group': group}
            if title:
                value['title'] = title
            collection.update_one(
                {'key': QR_ASSIGNMENTS_KEY},
                {'$set': {f'value.{group_id}': value}},
                upsert=True
            )
            client.close()
            return True
        return False
    except Exception as e:
        print(f"Failed to set QR group assignment: {e}")
        return False

def remove_qr_group_assignment(telegram_group_id):
    """Remove any logical QR config assignment for a Telegram group."""
    try:
        group_id = normalize_telegram_group_id(telegram_group_id)
        client = get_mongo_client()
        if client:
            db = client[MONGODB_DATABASE]
            collection = db[MONGODB_COLLECTION]
            result = collection.update_one(
                {'key': QR_ASSIGNMENTS_KEY},
                {'$unset': {f'value.{group_id}': ""}},
            )
            client.close()
            return result.modified_count > 0
        return False
    except Exception as e:
        print(f"Failed to remove QR group assignment: {e}")
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
