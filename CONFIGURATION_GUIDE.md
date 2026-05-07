# Telegram Group Factory - Configuration Guide

## Overview

This guide explains how to configure users to be added to newly created groups and manage backup QR code replication via the bot.

## Setting Up Default Users for New Groups

### What are Default Users?

Default users are a list of user IDs that will be **automatically added to every new group** created without explicitly specifying users.

### Step 1: Add Users to the Database

First, add the users you want to manage using the bot commands:

```
/add_user <username>
```

Example:
```
/add_user alice
/add_user bob
/add_user charlie
```

The bot will respond with:
```
✅ User alice added successfully (ID: 1234567890)
```

**Note:** Keep track of the user IDs returned by the bot - you'll need these for configuration.

### Step 2: View All Users

Check all available users in the database:

```
/users
```

This will show:
```
👥 All Users (3):
• alice (alice) - ID: 1234567890
• bob (bob) - ID: 0987654321
• charlie (charlie) - ID: 5555555555
```

### Step 3: Configure Default Users

#### Option A: Set Default Users (Replace Existing)
Replace the entire default users list:

```
/set_default_users 1234567890 0987654321 5555555555
```

Response:
```
✅ Default users updated successfully:
  • alice (ID: 1234567890)
  • bob (ID: 0987654321)
  • charlie (ID: 5555555555)
```

#### Option B: Add Users to Default List (Append)
Add new users to the existing default list:

```
/add_default_users 1111111111
```

Response:
```
✅ Users added to default list:
  • diana (ID: 1111111111)
```

#### Option C: Remove Users from Default List
Remove specific users from the default list:

```
/remove_default_users 5555555555
```

Response:
```
✅ Users removed from default list:
  • charlie (ID: 5555555555)
```

### Step 4: Verify Default Users

Check what users are currently configured as defaults:

```
/get_default_users
```

Response:
```
📋 Current default users for new groups:
  • alice (ID: 1234567890)
  • bob (ID: 0987654321)
  • diana (ID: 1111111111)
```

### Step 5: Create Groups with Default Users

Now whenever you create a new group **without specifying users**, all default users will be automatically added:

```
/create_group ProjectAlpha
```

This will automatically add alice, bob, and diana to the ProjectAlpha group.

You can also create a group with **specific users** (overriding defaults):

```
/create_group ProjectBeta 1234567890,0987654321
```

This will create ProjectBeta with only alice and bob, regardless of the default list.

---

## QR Code Backup Configuration

### What is QR Backup Data?

QR backup data is a code that can be used to replicate or restore your bot's session across multiple instances. This is useful for:
- Disaster recovery
- Multi-instance deployment
- Session migration
- Backup and restore scenarios

### Step 1: Generate or Obtain QR Code

Depending on your setup, you might have a QR code from:
- Bot session export
- Backup file
- Another instance

### Step 2: Set QR Backup Data

Store the QR backup data in the database:

```
/set_qr_backup YOUR_QR_CODE_HERE
```

Example:
```
/set_qr_backup 0001a8ac0123456789abcdef0123456789abcdef01234567
```

Response:
```
✅ QR backup data updated successfully!

Data: `0001a8ac0123456789abcdef0123456789abcdef01234567`
```

### Step 3: Retrieve QR Backup Data

Retrieve the stored QR backup data anytime:

```
/get_qr_backup
```

Response:
```
📊 Current QR Backup Data:
`0001a8ac0123456789abcdef0123456789abcdef01234567`
```

### Step 4: Use QR Backup for Replication

Once you have the QR backup data stored, you can:
1. Export it from the database
2. Use it in deployment scripts
3. Pass it to other bot instances
4. Store it in version control (encrypted) for DR purposes

---

## Database Structure

The configuration data is stored in MongoDB with the following structure:

### Default Users Collection (`group_config`)
```json
{
  "_id": ObjectId(...),
  "key": "default_users",
  "value": [1234567890, 0987654321, 1111111111]
}
```

### QR Backup Collection (`COLLECTION_NAME`)
```json
{
  "_id": ObjectId(...),
  "key": "qr_backup_data",
  "value": "0001a8ac0123456789abcdef0123456789abcdef01234567"
}
```

---

## Common Workflows

### Workflow 1: Initial Setup

```bash
# 1. Add users
/add_user alice
/add_user bob
/add_user charlie

# 2. Configure default users (save the IDs from step 1)
/set_default_users 1234567890 0987654321 5555555555

# 3. Verify configuration
/get_default_users

# 4. Create a test group
/create_group TestGroup
```

### Workflow 2: Adding New Users to Existing Groups

```bash
# 1. Add new user
/add_user diana

# 2. Add diana to default users
/add_default_users 1111111111

# 3. Future groups will include diana automatically
/create_group NewProject
```

### Workflow 3: QR Code Backup & Restore

```bash
# On source instance:
/get_qr_backup
# Copy the QR code output

# On target instance:
/set_qr_backup <paste_qr_code_here>

# Verify it was stored
/get_qr_backup
```

---

## Troubleshooting

### Issue: "No default users configured yet"
**Solution:** Run `/set_default_users` with at least one user ID.

### Issue: "User IDs {[123, 456]} do not exist in database"
**Solution:** First add these users with `/add_user <username>` and get their IDs.

### Issue: Group created but users not added
**Solution:** 
1. Check if default users are configured: `/get_default_users`
2. Verify users exist: `/users`
3. Manually add users to group: `/add_users <group_id> <user_id1>,<user_id2>`

### Issue: QR backup data appears empty
**Solution:** 
1. Check if data was stored: `/get_qr_backup`
2. Re-set the data: `/set_qr_backup <your_qr_code>`

---

## Environment Variables

Make sure these are set in your `.env` file:

```bash
TELETHON_API_ID=your_api_id
TELETHON_API_HASH=your_api_hash
TELEGRAM_BOT_TOKEN=your_bot_token
TELETHON_TOKEN=your_session_token

MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=groupfactory
MONGODB_COLLECTION=ghconfig

STAFF_CHAT_ID=your_staff_chat_id
FACTORY_BOT_ID=your_bot_id
```

---

## API Reference

### User Management Commands
- `/users` - List all users
- `/user <user_id>` - Get specific user info
- `/add_user <username>` - Add new user
- `/delete_user <user_id>` - Delete user

### Group Management Commands
- `/create_group <name>` - Create group with default users
- `/create_group <name> <id1>,<id2>` - Create group with specific users
- `/add_users <group_id> <id1>,<id2>` - Add users to existing group
- `/get_group <group_id>` - Get group information

### Configuration Commands
- `/get_default_users` - View current default users
- `/set_default_users <id1> <id2> ...` - Set default users (replace)
- `/add_default_users <id1> <id2> ...` - Add users to default list
- `/remove_default_users <id1> <id2> ...` - Remove users from default list
- `/get_qr_backup` - View QR backup data
- `/set_qr_backup <data>` - Set QR backup data
- `/config_help` - Show configuration command help
- `/help` - Show all available commands

---

## Advanced Usage

### Using in Docker Compose

```yaml
version: '3.8'
services:
  groupfactory:
    build: .
    environment:
      TELETHON_API_ID: ${TELETHON_API_ID}
      TELETHON_API_HASH: ${TELETHON_API_HASH}
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN}
      TELETHON_TOKEN: ${TELETHON_TOKEN}
      MONGODB_URI: mongodb://mongo:27017
      MONGODB_DATABASE: groupfactory
      MONGODB_COLLECTION: ghconfig
    depends_on:
      - mongo

  mongo:
    image: mongo:latest
    volumes:
      - mongo_data:/data/db

volumes:
  mongo_data:
```

### Accessing Configuration via MongoDB Client

```bash
# Connect to MongoDB
mongo mongodb://localhost:27017/groupfactory

# View default users
db.group_config.find()

# View QR backup
db.ghconfig.find({key: 'qr_backup_data'})
```

---

## Security Considerations

1. **Never share QR backup data** in public channels or version control
2. **Encrypt sensitive data** before storing in version control
3. **Rotate credentials regularly** especially after backups
4. **Limit bot access** to trusted chats only
5. **Monitor command usage** for suspicious activity

---

For more information or issues, check the project README.md or GitHub issues.
