import asyncio
import logging
import json
import uvicorn
from telethon import TelegramClient, events
from telethon.tl.types import InlineKeyboardMarkup, InlineKeyboardButton
from src.config import load_config, save_user_admin_role, get_user_admin_role
from src.services.mongodb_service import MongoDBService
from src.services.user_service import UserService
from src.services.group_service import GroupService
from src.handlers.user_handler import UserHandler
from src.handlers.group_handler import GroupHandler
from src.handlers.admin_handler import AdminHandler
from src.api.server import build_uvicorn_config, create_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    """Main application entry point"""
    logger.info("Starting telegram-groupfactory application")
    
    # Load configuration
    config = load_config()
    
    # Initialize MongoDB service
    mongo_service = MongoDBService(
        database_name=config['mongodb']['database'],
        collection_name=config['mongodb']['collection']
    )
    
    # Initialize services
    user_service = UserService(mongo_service)
    group_service = GroupService(mongo_service)
    
    # Initialize handlers
    user_handler = UserHandler(user_service)
    group_handler = GroupHandler(user_service, group_service)
    admin_handler = AdminHandler(user_service)
    
    # Create Telegram client
    client = TelegramClient(
        config['telegram']['session'],
        config['telegram']['api_id'],
        config['telegram']['api_hash']
    )
    
    @client.on(events.CallbackQuery())
    async def callback_handler(event):
        """Handle inline button callbacks for admin role selection"""
        try:
            data = event.data.decode() if isinstance(event.data, bytes) else event.data
            
            # Parse callback data
            if data.startswith('admin_role:'):
                user_id = event.sender_id
                is_full_admin = data.split(':')[1] == 'yes'
                
                # Save the user's admin role preference
                if save_user_admin_role(user_id, is_full_admin):
                    role_text = "✅ Full Group Admin" if is_full_admin else "👤 Regular Member"
                    await event.answer(f"Set as {role_text}")
                    
                    # Edit the message to show the selection
                    await event.edit(f"Group Admin Role Selection\n\n{role_text} - Confirmed!")
                else:
                    await event.answer("❌ Failed to save preference", alert=True)
            
            elif data.startswith('group_create:'):
                # Extract group name and user IDs from callback
                parts = data.split(':', 2)
                if len(parts) >= 3:
                    group_name = parts[1]
                    user_ids_str = parts[2]
                    
                    try:
                        user_ids = [int(uid) for uid in user_ids_str.split(',')] if user_ids_str else None
                        response = await group_handler.handle_create_group(group_name, user_ids)
                        await event.answer()
                        await event.edit(response)
                    except ValueError:
                        await event.answer("❌ Invalid user IDs", alert=True)
        
        except Exception as e:
            logger.error(f"Error handling callback: {e}")
            await event.answer(f"❌ Error: {str(e)}", alert=True)
    
    @client.on(events.NewMessage())
    async def message_handler(event):
        """Handle incoming messages and route to appropriate handlers"""
        message = event.message
        text = message.text or ""
        chat_id = event.chat_id
        sender_id = event.sender_id
        
        # Skip messages from bots
        if sender_id is None:
            return
        
        try:
            # ==================== ADMIN COMMANDS ====================
            # All admin commands require being in the admin chat
            
            if text.startswith('/admin_get_users'):
                response = await admin_handler.handle_get_default_users(chat_id)
                await event.respond(response)
            
            elif text.startswith('/admin_set_users'):
                # Parse user IDs from command
                parts = text.split()
                if len(parts) > 1:
                    try:
                        user_ids = [int(uid) for uid in parts[1:]]
                        response = await admin_handler.handle_set_default_users(chat_id, user_ids)
                        await event.respond(response)
                    except ValueError:
                        await event.respond("❌ Invalid user IDs. Please provide numeric IDs.\n\nUsage: `/admin_set_users <user_id1> <user_id2> ...`")
                else:
                    await event.respond("❌ Please provide at least one user ID.\n\nUsage: `/admin_set_users <user_id1> <user_id2> ...`")
            
            elif text.startswith('/admin_add_users'):
                # Parse user IDs from command
                parts = text.split()
                if len(parts) > 1:
                    try:
                        user_ids = [int(uid) for uid in parts[1:]]
                        response = await admin_handler.handle_add_to_default_users(chat_id, user_ids)
                        await event.respond(response)
                    except ValueError:
                        await event.respond("❌ Invalid user IDs. Please provide numeric IDs.\n\nUsage: `/admin_add_users <user_id1> <user_id2> ...`")
                else:
                    await event.respond("❌ Please provide at least one user ID.\n\nUsage: `/admin_add_users <user_id1> <user_id2> ...`")
            
            elif text.startswith('/admin_remove_users'):
                # Parse user IDs from command
                parts = text.split()
                if len(parts) > 1:
                    try:
                        user_ids = [int(uid) for uid in parts[1:]]
                        response = await admin_handler.handle_remove_from_default_users(chat_id, user_ids)
                        await event.respond(response)
                    except ValueError:
                        await event.respond("❌ Invalid user IDs. Please provide numeric IDs.\n\nUsage: `/admin_remove_users <user_id1> <user_id2> ...`")
                else:
                    await event.respond("❌ Please provide at least one user ID.\n\nUsage: `/admin_remove_users <user_id1> <user_id2> ...`")
            
            elif text.startswith('/admin_add_user'):
                # Parse username from command
                parts = text.split(maxsplit=1)
                if len(parts) > 1:
                    username = parts[1].strip()
                    response = await admin_handler.handle_add_user_to_db(chat_id, username)
                    await event.respond(response)
                else:
                    await event.respond("❌ Please provide a username.\n\nUsage: `/admin_add_user <username>`")
            
            elif text.startswith('/admin_get_qr'):
                response = await admin_handler.handle_get_qr_backup(chat_id)
                await event.respond(response)
            
            elif text.startswith('/admin_set_qr'):
                # Parse QR data from command
                parts = text.split(maxsplit=1)
                if len(parts) > 1:
                    qr_data = parts[1].strip()
                    response = await admin_handler.handle_set_qr_backup(chat_id, qr_data)
                    await event.respond(response)
                else:
                    await event.respond("❌ Please provide QR backup data.\n\nUsage: `/admin_set_qr <qr_code>`")
            
            elif text.startswith('/admin_help'):
                response = await admin_handler.handle_admin_help(chat_id)
                await event.respond(response)
            
            # ==================== GROUP COMMANDS ====================
            
            elif text.startswith('/create_group'):
                # Parse group name and optional user IDs
                parts = text.split(maxsplit=2)
                if len(parts) > 1:
                    group_name = parts[1]
                    user_ids = None
                    if len(parts) > 2:
                        try:
                            user_ids = [int(uid) for uid in parts[2].split(',')]
                        except ValueError:
                            await event.respond("❌ Invalid user IDs format.\n\nUsage: `/create_group <name>` or `/create_group <name> <user_id1>,<user_id2>,...`")
                            return
                    
                    # Create the group
                    response = await group_handler.handle_create_group(group_name, user_ids)
                    
                    # Ask about admin role with inline buttons
                    buttons = InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton(text="✅ Yes, I want to be full admin", data=b"admin_role:yes"),
                            InlineKeyboardButton(text="❌ No, just regular member", data=b"admin_role:no")
                        ]
                    ])
                    
                    await event.respond(
                        f"{response}\n\n" +
                        "👤 Would you like to be added as a full admin to this group?",
                        buttons=buttons
                    )
                else:
                    await event.respond("❌ Please provide a group name.\n\nUsage: `/create_group <name>` or `/create_group <name> <user_id1>,<user_id2>,...`")
            
            elif text.startswith('/add_users'):
                # Parse group ID and user IDs
                parts = text.split(maxsplit=2)
                if len(parts) > 2:
                    try:
                        group_id = parts[1]
                        user_ids = [int(uid) for uid in parts[2].split(',')]
                        response = await group_handler.handle_add_users(group_id, user_ids)
                        await event.respond(response)
                    except ValueError:
                        await event.respond("❌ Invalid format.\n\nUsage: `/add_users <group_id> <user_id1>,<user_id2>,...`")
                else:
                    await event.respond("❌ Please provide group ID and user IDs.\n\nUsage: `/add_users <group_id> <user_id1>,<user_id2>,...`")
            
            elif text.startswith('/get_group'):
                # Parse group ID
                parts = text.split()
                if len(parts) > 1:
                    group_id = parts[1]
                    response = await group_handler.handle_get_group_info(group_id)
                    await event.respond(response)
                else:
                    await event.respond("❌ Please provide a group ID.\n\nUsage: `/get_group <group_id>`")
            
            # ==================== USER COMMANDS ====================
            
            elif text.startswith('/users') or text.startswith('/get_users'):
                response = await user_handler.handle_get_all_users()
                await event.respond(response)
            
            elif text.startswith('/user'):
                # Parse user ID
                parts = text.split()
                if len(parts) > 1:
                    try:
                        user_id = int(parts[1])
                        response = await user_handler.handle_get_user_by_id(user_id)
                        await event.respond(response)
                    except ValueError:
                        await event.respond("❌ Invalid user ID. Please provide a numeric ID.\n\nUsage: `/user <user_id>`")
                else:
                    await event.respond("❌ Please provide a user ID.\n\nUsage: `/user <user_id>`")
            
            elif text.startswith('/add_user'):
                # Parse username
                parts = text.split(maxsplit=1)
                if len(parts) > 1:
                    username = parts[1].strip()
                    response = await user_handler.handle_add_user(username)
                    await event.respond(response)
                else:
                    await event.respond("❌ Please provide a username.\n\nUsage: `/add_user <username>`")
            
            elif text.startswith('/delete_user'):
                # Parse user ID
                parts = text.split()
                if len(parts) > 1:
                    try:
                        user_id = int(parts[1])
                        response = await user_handler.handle_delete_user(user_id)
                        await event.respond(response)
                    except ValueError:
                        await event.respond("❌ Invalid user ID. Please provide a numeric ID.\n\nUsage: `/delete_user <user_id>`")
                else:
                    await event.respond("❌ Please provide a user ID.\n\nUsage: `/delete_user <user_id>`")
            
            # ==================== HELP COMMAND ====================
            
            elif text.startswith('/help'):
                help_text = """📖 Available Commands:

**User Management:**
• `/users` - List all users
• `/user <user_id>` - Get user info
• `/add_user <username>` - Add new user
• `/delete_user <user_id>` - Delete user

**Group Management:**
• `/create_group <name>` - Create group with default users
• `/create_group <name> <id1>,<id2>` - Create group with specific users
• `/add_users <group_id> <id1>,<id2>` - Add users to group
• `/get_group <group_id>` - Get group info

**Admin Commands (Admin Chat Only):**
• `/admin_get_users` - Show default group users
• `/admin_set_users <id1> <id2>` - Set default users
• `/admin_add_users <id1> <id2>` - Add users to default list
• `/admin_remove_users <id1> <id2>` - Remove users from default list
• `/admin_add_user <username>` - Add new user to database
• `/admin_get_qr` - Get QR backup data
• `/admin_set_qr <data>` - Set QR backup data
• `/admin_help` - Show admin command help"""
                await event.respond(help_text)
                
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await event.respond(f"❌ An error occurred: {str(e)}")
    
    # Build the internal REST API alongside the Telegram client
    api_app = create_app(config, user_handler, group_handler, admin_handler)
    api_server = uvicorn.Server(build_uvicorn_config(api_app))

    try:
        # Start the client
        await client.start()
        logger.info("Telegram client started successfully")

        # Run the Telegram client and the REST API concurrently. If either
        # exits, cancel the other so the process shuts down cleanly.
        telegram_task = asyncio.create_task(client.run_until_disconnected(), name="telegram")
        api_task = asyncio.create_task(api_server.serve(), name="rest-api")

        done, pending = await asyncio.wait(
            {telegram_task, api_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()
        for task in pending:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        for task in done:
            exc = task.exception()
            if exc is not None:
                logger.error(f"{task.get_name()} task failed: {exc}")

    except Exception as e:
        logger.error(f"Error in main application: {e}")
    finally:
        # Ask uvicorn to shut down if it's still running
        api_server.should_exit = True
        # Clean up connections
        mongo_service.close()
        logger.info("Application shutdown complete")

if __name__ == "__main__":
    asyncio.run(main())
