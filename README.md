<!-- gitea-mirror-notice:start -->
> [!IMPORTANT]
> **This GitHub repository is a mirror.**  
> The canonical public repository is [https://git.mulas.me/corrado/telegram-groupfactory](https://git.mulas.me/corrado/telegram-groupfactory).
<!-- gitea-mirror-notice:end -->

# telegram-groupfactory

A Telegram user API service for managing groups with MongoDB backend and admin-only configuration.

## Features

- ✅ Create and manage Telegram groups with default user lists
- ✅ Admin-only configuration (requires STAFF_CHAT_ID)
- ✅ User management with MongoDB storage
- ✅ GroupHelp settings backup payload rendered as a QR image for `.importbackup`
- ✅ Interactive admin role selection for group creators
- ✅ Modular architecture with separation of concerns
- ✅ Telegram user API integration using Telethon

## Architecture

The application follows a modular architecture with the following components:

1. **Configuration**: `src/config.py` - Application configuration with admin access control
2. **Data Models**: `src/models/` - Data models for users and groups
3. **Services**: `src/services/` - Business logic for user and group operations
4. **Handlers**: 
   - `src/handlers/user_handler.py` - User management commands
   - `src/handlers/group_handler.py` - Group management commands
   - `src/handlers/admin_handler.py` - **Admin-only configuration commands**
5. **Main Application**: `src/main.py` - Entry point with callback and message routing

## Setup

1. Create a `.env` file with your Telegram API credentials:
   ```
   TELETHON_API_ID=your_api_id
   TELETHON_API_HASH=your_api_hash
   TELETHON_TOKEN=your_session_token
   
   MONGODB_URI=mongodb://localhost:27017
   MONGODB_DATABASE=groupfactory
   MONGODB_COLLECTION=ghconfig
   
   STAFF_CHAT_ID=your_admin_chat_id
   FACTORY_BOT_ID=your_bot_id
   FACTORY_BOT_USERNAME=your_bot_username
   ```

   Generate `TELETHON_TOKEN` with:
   ```bash
   TELETHON_API_ID=your_api_id TELETHON_API_HASH=your_api_hash \
     python3 scripts/generate_telegram_session.py
   ```

   The script performs a Telegram user login and prints the `TELETHON_TOKEN`
   value to store in the Kubernetes Secret.

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the application:
   ```bash
   python -m src.main
   ```

## Docker

To run with Docker:
```bash
docker build -t telegram-groupfactory .
docker run telegram-groupfactory
```

## REST API

The userbot also exposes an internal FastAPI surface on `API_HOST:API_PORT`
for the separate conventional Telegram bot. Requests require `X-API-Key`.

Relevant bot-facing endpoints:

```text
POST   /api/groups
GET    /api/admin/default-users
PUT    /api/admin/default-users
POST   /api/admin/default-users
DELETE /api/admin/default-users
GET    /api/admin/qr-backup?qr_group=default
PUT    /api/admin/qr-backup
POST   /api/admin/qr-backup/image
GET    /api/admin/qr-groups
POST   /api/admin/qr-groups/{qr_group}/assignments
DELETE /api/admin/qr-groups/assignments
POST   /api/admin/qr-sync
```

## Documentation

- **[ADMIN_IMPLEMENTATION.md](ADMIN_IMPLEMENTATION.md)** - Admin-only configuration features
- **[CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md)** - Complete user guide

## Quick Start

### GroupFactory Commands (Staff Chat Only)
```
!newgrp                         - Start interactive group creation
!confirm                        - Confirm pending group creation
!cancel                         - Cancel pending group creation
!PING                           - Check if the userbot is online
!help                           - Show GroupFactory commands
```

### Admin Commands (Admin Chat Only)
```
/admin_add_user <username_or_id:username> - Add user to database
/admin_add_user                   - Add a forwarded user to database
/admin_set_users <id_or_username_or_id:username> ...  - Set default users for groups
/admin_add_users <id_or_username_or_id:username> ...  - Add users to default list
/admin_add_users                  - Add a forwarded user to default list
/admin_remove_users <id_or_username_or_id:username>   - Remove users from default list
/admin_get_users                  - Show current default users
/admin_get_qr [qr_group]          - Retrieve GroupHelp backup QR data
/admin_set_qr [qr_group] <payload> - Store GroupHelp backup payload
/admin_set_qr                     - Decode forwarded QR image for default config
/admin_set_qr_group <qr_group>    - Decode forwarded QR image for named config
/admin_qr_groups [qr_group]       - List QR configs and assigned Telegram groups
/admin_qr_group_add <qr_group> <group_id> ... - Assign groups to QR config
/admin_qr_group_remove <group_id> ... - Remove QR config assignment
/admin_sync_qr [qr_group|all]     - Send stored `.importbackup` QR to owned assigned groups
```

### Legacy User Commands
```
/create_group <name>              - Deprecated; use !newgrp in staff chat
/users                            - List all users
/user <user_id>                   - Get user info
/help                             - Show all available commands
```

## Available Commands

- `!newgrp` - Create a new group with DB users and stored GroupHelp QR import
- `/create_group <name>` - Deprecated; use `!newgrp`
- `/add_users <group_id> <user_ids>` - Add users to a group
- `/get_group <group_id>` - Get group information
- `/users` - List all users
- `/user <user_id>` - Get user information
- `/add_user <user_id> <username> <name>` - Add a new user
- `/delete_user <user_id>` - Delete a user
