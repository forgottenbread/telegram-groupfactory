# telegram-groupfactory

A Telegram user API service for managing groups with MongoDB backend and admin-only configuration.

## Features

- ✅ Create and manage Telegram groups with default user lists
- ✅ Admin-only configuration (requires STAFF_CHAT_ID)
- ✅ User management with MongoDB storage
- ✅ GroupHelp settings backup QR storage for `.importbackup`
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
   python src/main.py
   ```

## Docker

To run with Docker:
```bash
docker build -t telegram-groupfactory .
docker run telegram-groupfactory
```

## Documentation

- **[ADMIN_IMPLEMENTATION.md](ADMIN_IMPLEMENTATION.md)** - Admin-only configuration features
- **[CONFIGURATION_GUIDE.md](CONFIGURATION_GUIDE.md)** - Complete user guide

## Quick Start

### Admin Commands (Admin Chat Only)
```
/admin_add_user <username>        - Add user to database
/admin_set_users <id1> <id2> ...  - Set default users for groups
/admin_add_users <id1> <id2> ...  - Add users to default list
/admin_remove_users <id1> <id2>   - Remove users from default list
/admin_get_users                  - Show current default users
/admin_set_qr <qr_code>           - Store GroupHelp backup QR data
/admin_get_qr                     - Retrieve GroupHelp backup QR data
```

### User Commands
```
/create_group <name>              - Create group with default users
/users                            - List all users
/user <user_id>                   - Get user info
/help                             - Show all available commands
```

## Available Commands

- `/create_group <name>` - Create a new group
- `/add_users <group_id> <user_ids>` - Add users to a group
- `/get_group <group_id>` - Get group information
- `/users` - List all users
- `/user <user_id>` - Get user information
- `/add_user <user_id> <username> <name>` - Add a new user
- `/delete_user <user_id>` - Delete a user
