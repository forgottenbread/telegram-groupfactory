import asyncio
import logging
import uvicorn
from telethon import TelegramClient, events
from src.config import load_config
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
    staff_chat_id = config['telegram']['staff_chat_id']
    factory_bot_id = config['telegram']['factory_bot_id']
    
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
    group_service.set_client(client)
    group_conversations = {}

    async def create_group_from_staff_flow(event, name: str, description: str):
        response = await group_handler.handle_create_group(
            name,
            description=description,
            status_callback=event.respond,
            staff_chat_id=staff_chat_id,
            factory_bot_id=factory_bot_id,
        )
        await event.respond(response)

    def is_staff_chat(chat_id: int) -> bool:
        return chat_id == staff_chat_id
    
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
            # ==================== IMS GROUPFACTORY STAFF FLOW ====================
            if is_staff_chat(chat_id):
                raw_text = text.strip()
                lower_text = raw_text.lower()

                if lower_text == '!ping':
                    await event.respond('PONG -> IMS GroupFactory Userbot')
                    return

                if lower_text == '!help':
                    help_text = """**IMS GroupFactory Commands**

`!newgrp` - Start creating a new Telegram group
`!cancel` - Cancel the current operation
`!confirm` - Confirm group creation
`!PING` - Check if the userbot is online
`!help` - Display this help message"""
                    await event.respond(help_text)
                    return

                if lower_text == '!cancel':
                    if sender_id in group_conversations:
                        del group_conversations[sender_id]
                        await event.respond('🛑 Operation canceled.')
                    else:
                        await event.respond('❓ No active operation to cancel.')
                    return

                if lower_text.startswith('!newgrp'):
                    if lower_text != '!newgrp':
                        cmd_args = raw_text[len('!newgrp'):].strip()
                        marker = "\n\nDescription:\n"
                        if marker in cmd_args:
                            name, description = cmd_args.split(marker, 1)
                            name = name.strip()
                            description = description.strip()
                            if not name or not description:
                                await event.respond('⚠️ Group name and description cannot be empty.')
                                return
                            await create_group_from_staff_flow(event, name, description)
                        else:
                            await event.respond('⚠️ Old format detected but missing description.\nUse `!newgrp` alone to start interactive mode.')
                        return

                    group_conversations[sender_id] = {
                        'step': 'name',
                        'data': {}
                    }
                    await event.respond('👋 Let\'s create a new group!\n\nPlease enter the group name:')
                    return

                if sender_id in group_conversations:
                    current_step = group_conversations[sender_id]['step']

                    if lower_text == '!confirm' and current_step == 'confirm':
                        name = group_conversations[sender_id]['data']['name']
                        description = group_conversations[sender_id]['data']['description']
                        await event.respond('✅ Confirmed! Starting group creation process...')
                        try:
                            await create_group_from_staff_flow(event, name, description)
                        finally:
                            group_conversations.pop(sender_id, None)
                        return

                    if raw_text.startswith('!'):
                        if current_step == 'confirm':
                            await event.respond('❓ Please type `!confirm` to create the group or `!cancel` to abort.')
                        return

                    if current_step == 'name':
                        if not raw_text:
                            await event.respond('⚠️ Group name cannot be empty. Please try again:')
                            return

                        group_conversations[sender_id]['data']['name'] = raw_text
                        group_conversations[sender_id]['step'] = 'description'
                        await event.respond(f'📝 Group name set to: "{raw_text}"\n\nNow please enter the group description:')
                        return

                    if current_step == 'description':
                        if not raw_text:
                            await event.respond('⚠️ Group description cannot be empty. Please try again:')
                            return

                        group_conversations[sender_id]['data']['description'] = raw_text
                        name = group_conversations[sender_id]['data']['name']
                        group_conversations[sender_id]['step'] = 'confirm'
                        await event.respond(
                            f'📋 **Group Creation Summary**\n\n'
                            f'**Name**: {name}\n'
                            f'**Description**: {raw_text}\n\n'
                            f'Type `!confirm` to create this group or `!cancel` to abort.'
                        )
                        return

                    if current_step == 'confirm':
                        await event.respond('❓ Please type `!confirm` to create the group or `!cancel` to abort.')
                        return

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
                await event.respond("ℹ️ `/create_group` has been replaced. Use `!newgrp` in the staff chat.")
            
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
• `!newgrp` - Create a group with database users and stored GroupHelp QR import
• `/create_group` - Deprecated; use `!newgrp`
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
