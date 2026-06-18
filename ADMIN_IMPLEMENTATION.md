# Admin-Only Configuration Implementation

## Overview

The telegram-groupfactory bot now has **admin-only configuration** where configuration operations (adding/modifying users, setting GroupHelp QR backups) can ONLY be executed from the designated admin chat (STAFF_CHAT_ID).

## Key Features

### 1. **Admin Access Control**

All configuration commands are **restricted to the admin chat only**:
- If executed from any other chat, the user receives: `❌ Admin commands can only be executed in the admin chat`
- Admin chat ID is configured via the `STAFF_CHAT_ID` environment variable

### 2. **Admin-Only Commands**

The following commands can ONLY be run from the admin chat:

#### User Management
```
/admin_add_user <username>        - Add new user to database
/admin_get_users                  - View default users list
/admin_set_users <id1> <id2> ...  - Replace entire default users list
/admin_add_users <id1> <id2> ...  - Add users to default list
/admin_remove_users <id1> <id2>   - Remove users from default list
```

#### GroupHelp QR Code Backup
```
/admin_get_qr                     - Retrieve GroupHelp backup QR data
/admin_set_qr <qr_code>           - Store GroupHelp backup QR data for `.importbackup`
```

#### Help
```
/admin_help                       - Show all admin commands
```

### 3. **Group Creation with Admin Role Selection**

When a user creates a group with `/create_group <name>`, they are presented with **inline buttons**:

```
Group Admin Role Selection

Would you like to be added as a full admin to this group?

[✅ Yes, I want to be full admin]  [❌ No, just regular member]
```

**User's preference is stored in MongoDB** (`user_admin_roles` collection):
```json
{
  "user_id": 123456789,
  "is_full_admin": true
}
```

### 4. **Auto-Save User Preferences**

- When a user clicks a button, their preference is saved
- The preference persists across sessions
- Can be retrieved later using `get_user_admin_role(user_id)`

## Implementation Details

### Config Module Updates (`src/config.py`)

New functions:
- `is_admin_chat(chat_id: int) -> bool` - Verify if message is from admin chat
- `verify_admin_access(chat_id: int) -> tuple` - Check access and return error message if not admin
- `save_user_admin_role(user_id: int, is_full_admin: bool) -> bool` - Store user's admin preference
- `get_user_admin_role(user_id: int) -> bool` - Retrieve user's admin preference

### New Admin Handler (`src/handlers/admin_handler.py`)

New class `AdminHandler` with methods:
- `verify_access(chat_id: int)` - Check admin access
- `handle_get_default_users(chat_id)` - Get default users (admin only)
- `handle_set_default_users(chat_id, user_ids)` - Set default users (admin only)
- `handle_add_to_default_users(chat_id, user_ids)` - Add users (admin only)
- `handle_remove_from_default_users(chat_id, user_ids)` - Remove users (admin only)
- `handle_add_user_to_db(chat_id, username)` - Add user (admin only)
- `handle_get_qr_backup(chat_id)` - Get GroupHelp QR backup (admin only)
- `handle_set_qr_backup(chat_id, qr_data)` - Set GroupHelp QR backup (admin only)
- `handle_admin_help(chat_id)` - Show admin help (admin only)

### Main Application Updates (`src/main.py`)

**New imports:**
- `events` from telethon (for callback query handling)
- `InlineKeyboardMarkup`, `InlineKeyboardButton` from telethon.tl.types
- `AdminHandler` from handlers
- `save_user_admin_role`, `get_user_admin_role` from config

**New features:**
1. **Callback Query Handler** - Handles inline button clicks:
   - `admin_role:yes` - User wants to be full admin
   - `admin_role:no` - User wants to be regular member

2. **Message Handler Updates** - New `/admin_*` command routing

3. **Inline Buttons** - Shown after group creation asking about admin role

## Usage Example

### Admin Setup (in admin chat)
```
Admin: /admin_add_user alice
Bot: ✅ User alice added successfully (ID: 1234567890)

Admin: /admin_add_user bob  
Bot: ✅ User bob added successfully (ID: 0987654321)

Admin: /admin_set_users 1234567890 0987654321
Bot: ✅ Default users updated successfully:
  • alice (ID: 1234567890)
  • bob (ID: 0987654321)

Admin: /admin_set_qr 0001a8ac0123456789abcdef...
Bot: ✅ QR backup data updated successfully!
```

### User Usage (any chat)
```
User: /create_group ProjectAlpha
Bot: ✅ Group 'ProjectAlpha' created successfully with ID: ...

[Inline buttons appear]
👤 Would you like to be added as a full admin to this group?

User: [clicks "Yes, I want to be full admin"]
Bot: Set as ✅ Full Group Admin - Confirmed!
```

## Access Control Features

1. **Chat-Level Access Control** - Only STAFF_CHAT_ID can execute admin commands
2. **Database Persistence** - All preferences stored in MongoDB
3. **Role Selection** - Users explicitly choose their role when creating groups
4. **Admin Preference Storage** - Preferences persist across sessions

## Database Collections

### `group_config` Collection
Stores default users and system configurations:
```json
{
  "key": "default_users",
  "value": [1234567890, 0987654321]
}
```

### `user_admin_roles` Collection
Stores per-user admin preferences:
```json
{
  "user_id": 123456789,
  "is_full_admin": true,
  "_id": ObjectId(...)
}
```

### `ghconfig` Collection
Stores GroupHelp backup QR data:
```json
{
  "key": "qr_backup_data",
  "value": "0001a8ac0123456789abcdef..."
}
```

## Environment Variables Required

```bash
STAFF_CHAT_ID=your_admin_chat_id          # Admin chat ID for config access
TELETHON_API_ID=your_api_id
TELETHON_API_HASH=your_api_hash
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=groupfactory
MONGODB_COLLECTION=ghconfig
```

## Error Messages

| Scenario | Message |
|----------|---------|
| Admin cmd from non-admin chat | `❌ Admin commands can only be executed in the admin chat (ID: XXX)` |
| Invalid user ID format | `❌ Invalid user IDs. Please provide numeric IDs.` |
| User not found in database | `❌ No valid users found. User IDs [...] do not exist in database.` |
| Failed to save | `❌ Failed to save [configuration/preference]` |

## Testing

### Test Admin Access Control
```bash
# In non-admin chat:
/admin_get_users
# Should respond: ❌ Admin commands can only be executed in the admin chat

# In admin chat:
/admin_get_users  
# Should work and show users
```

### Test User Preferences
```bash
# Create group (user chooses admin role via button)
/create_group TestGroup

# User's preference saved to MongoDB
# Can retrieve with: get_user_admin_role(user_id)
```

### Test GroupHelp QR Backup
```bash
# In admin chat:
/admin_set_qr myqrcode123
# ✅ QR backup data updated successfully!

/admin_get_qr
# 📊 Current QR Backup Data: myqrcode123

# In the target group:
.importbackup myqrcode123
```

## Future Enhancements

- Add `/admin_list_user_roles` - Show all users and their role preferences
- Add `/admin_modify_user_role <user_id> <admin|member>` - Change existing user roles
- Add audit logging for admin commands
- Add `/admin_backup` - Backup all configurations
- Add `/admin_restore` - Restore from backup
