import asyncio
import logging
import uvicorn
from telethon import TelegramClient, events, types
from src.config import DEFAULT_QR_GROUP, load_config
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
    factory_bot_username = config['telegram']['factory_bot_username']
    
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
    admin_handler.set_client(client)
    group_conversations = {}
    qr_import_sessions = {}
    user_import_sessions = {}
    background_tasks = {"grouphelp_qr_sync": None}

    async def create_group_from_staff_flow(event, name: str, description: str):
        response = await group_handler.handle_create_group(
            name,
            description=description,
            status_callback=event.respond,
            staff_chat_id=staff_chat_id,
            factory_bot_id=factory_bot_id,
            factory_bot_username=factory_bot_username,
        )
        await event.respond(response)

    def is_staff_chat(chat_id: int) -> bool:
        return chat_id == staff_chat_id

    def is_importbackup_body(raw_text: str) -> bool:
        return (raw_text or "").strip().lower() in (".importbackup", "/importbackup")

    def has_image_media(message) -> bool:
        if getattr(message, "photo", None):
            return True
        document = getattr(message, "document", None)
        mime_type = getattr(document, "mime_type", "") if document else ""
        return mime_type.startswith("image/")

    async def handle_forwarded_qr_import(event, raw_text: str, qr_group: str = DEFAULT_QR_GROUP) -> str:
        message = event.message
        if not message.fwd_from:
            return "❌ Please forward the original GroupHelp QR image message. Do not upload or paste it manually."
        if not is_importbackup_body(raw_text):
            return "❌ Forwarded QR message must have `.importbackup` as its caption/body."
        if not message.media or not has_image_media(message):
            return "❌ Forwarded `.importbackup` message must contain a QR image."

        image_bytes = await client.download_media(message, file=bytes)
        if not image_bytes:
            return "❌ Could not download the forwarded QR image."

        return await admin_handler.handle_set_qr_backup_from_image(event.chat_id, image_bytes, qr_group=qr_group)

    async def handle_forwarded_user_import(event, add_to_defaults: bool) -> str:
        message = event.message
        forward_info = getattr(message, "fwd_from", None)
        if not forward_info:
            return "❌ Please forward a message from the Telegram user. Do not paste a numeric ID."

        from_id = getattr(forward_info, "from_id", None)
        if not isinstance(from_id, types.PeerUser):
            return "❌ Forwarded message must come from a Telegram user, not a channel/group or hidden sender."

        try:
            entity = await client.get_entity(from_id)
        except Exception as e:
            return f"❌ Could not resolve forwarded user entity: {e}"

        return await admin_handler.handle_add_user_entity(
            event.chat_id,
            entity,
            add_to_defaults=add_to_defaults,
        )
    
    @client.on(events.NewMessage())
    async def message_handler(event):
        """Handle incoming messages and route to appropriate handlers"""
        message = event.message
        text = getattr(message, "raw_text", None) or getattr(message, "text", None) or getattr(message, "message", "") or ""
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
                    await event.respond('PONG - GroupFactory Service Userbot')
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
                    canceled = False
                    if sender_id in group_conversations:
                        del group_conversations[sender_id]
                        canceled = True
                    if sender_id in qr_import_sessions:
                        del qr_import_sessions[sender_id]
                        canceled = True
                    if sender_id in user_import_sessions:
                        del user_import_sessions[sender_id]
                        canceled = True

                    if canceled:
                        await event.respond('🛑 Operation canceled.')
                    else:
                        await event.respond('❓ No active operation to cancel.')
                    return

                if (
                    sender_id in qr_import_sessions
                    and not lower_text.startswith('/admin_set_qr')
                    and (message.fwd_from or not raw_text.startswith('/'))
                ):
                    session = qr_import_sessions[sender_id]
                    if session["chat_id"] != chat_id:
                        return

                    response = await handle_forwarded_qr_import(
                        event,
                        raw_text,
                        qr_group=session.get("qr_group", DEFAULT_QR_GROUP),
                    )
                    if response.startswith("✅"):
                        qr_import_sessions.pop(sender_id, None)
                    await event.respond(response)
                    return

                if (
                    sender_id in user_import_sessions
                    and (message.fwd_from or not raw_text.startswith('/'))
                ):
                    session = user_import_sessions[sender_id]
                    if session["chat_id"] != chat_id:
                        return

                    response = await handle_forwarded_user_import(
                        event,
                        add_to_defaults=session["add_to_defaults"],
                    )
                    if response.startswith("✅"):
                        user_import_sessions.pop(sender_id, None)
                    await event.respond(response)
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
                parts = text.split()
                if len(parts) > 1:
                    response = await admin_handler.handle_set_default_users(chat_id, parts[1:])
                    await event.respond(response)
                else:
                    await event.respond("❌ Please provide at least one user ID, username, or id:username pair.\n\nUsage: `/admin_set_users <id_or_username_or_id:username> ...`")
            
            elif text.startswith('/admin_add_users'):
                parts = text.split()
                if len(parts) > 1:
                    response = await admin_handler.handle_add_to_default_users(chat_id, parts[1:])
                    user_import_sessions.pop(sender_id, None)
                    qr_import_sessions.pop(sender_id, None)
                    await event.respond(response)
                else:
                    is_admin, error = admin_handler.verify_access(chat_id)
                    if not is_admin:
                        await event.respond(error)
                    else:
                        user_import_sessions[sender_id] = {
                            "chat_id": chat_id,
                            "add_to_defaults": True,
                        }
                        qr_import_sessions.pop(sender_id, None)
                        await event.respond(
                            "👤 Forward a message from the Telegram user to add them to the database and default group users.\n\n"
                            "The forward must expose the sender. Send `!cancel` to abort."
                        )
            
            elif text.startswith('/admin_remove_users'):
                parts = text.split()
                if len(parts) > 1:
                    response = await admin_handler.handle_remove_from_default_users(chat_id, parts[1:])
                    await event.respond(response)
                else:
                    await event.respond("❌ Please provide at least one user ID, username, or id:username pair.\n\nUsage: `/admin_remove_users <id_or_username_or_id:username> ...`")
            
            elif text.startswith('/admin_add_user'):
                parts = text.split(maxsplit=1)
                if len(parts) > 1:
                    username = parts[1].strip()
                    response = await admin_handler.handle_add_user_to_db(chat_id, username)
                    user_import_sessions.pop(sender_id, None)
                    qr_import_sessions.pop(sender_id, None)
                    await event.respond(response)
                else:
                    is_admin, error = admin_handler.verify_access(chat_id)
                    if not is_admin:
                        await event.respond(error)
                    else:
                        user_import_sessions[sender_id] = {
                            "chat_id": chat_id,
                            "add_to_defaults": False,
                        }
                        qr_import_sessions.pop(sender_id, None)
                        await event.respond(
                            "👤 Forward a message from the Telegram user to add them to the database.\n\n"
                            "The forward must expose the sender. Send `!cancel` to abort."
                        )
            
            elif text.startswith('/admin_get_qr'):
                parts = text.split(maxsplit=1)
                qr_group = parts[1].strip() if len(parts) > 1 else DEFAULT_QR_GROUP
                response = await admin_handler.handle_get_qr_backup(chat_id, qr_group=qr_group)
                await event.respond(response)

            elif text.startswith('/admin_sync_qr'):
                is_admin, error = admin_handler.verify_access(chat_id)
                if not is_admin:
                    await event.respond(error)
                else:
                    current_task = background_tasks.get("grouphelp_qr_sync")
                    if current_task and not current_task.done():
                        await event.respond("ℹ️ GroupHelp QR sync is already running.")
                    else:
                        parts = text.split(maxsplit=1)
                        sync_group = parts[1].strip().lower() if len(parts) > 1 else DEFAULT_QR_GROUP

                        async def send_sync_status(message: str):
                            return await client.send_message(chat_id, message)

                        async def run_grouphelp_qr_sync():
                            try:
                                if sync_group == "all":
                                    await group_service.sync_all_grouphelp_qr_groups(
                                        status_callback=send_sync_status,
                                        delay_seconds=30,
                                    )
                                else:
                                    await group_service.sync_grouphelp_qr_to_owned_groups(
                                        status_callback=send_sync_status,
                                        delay_seconds=30,
                                        qr_group=sync_group,
                                    )
                            except Exception as e:
                                logger.error(f"GroupHelp QR sync task failed: {e}")
                                await client.send_message(chat_id, f"❌ GroupHelp QR sync failed: {e}")
                            finally:
                                background_tasks["grouphelp_qr_sync"] = None

                        background_tasks["grouphelp_qr_sync"] = asyncio.create_task(
                            run_grouphelp_qr_sync(),
                            name="grouphelp-qr-sync",
                        )
                        await event.respond(f"✅ GroupHelp QR sync `{sync_group}` started in background.")

            elif text.startswith('/admin_qr_group_add'):
                parts = text.split()
                if len(parts) > 2:
                    response = await admin_handler.handle_assign_qr_group(chat_id, parts[1], parts[2:])
                    await event.respond(response)
                else:
                    await event.respond("❌ Usage: `/admin_qr_group_add <qr_group> <telegram_group_id> ...`")

            elif text.startswith('/admin_qr_group_remove'):
                parts = text.split()
                if len(parts) > 1:
                    response = await admin_handler.handle_remove_qr_group_assignment(chat_id, parts[1:])
                    await event.respond(response)
                else:
                    await event.respond("❌ Usage: `/admin_qr_group_remove <telegram_group_id> ...`")

            elif text.startswith('/admin_qr_groups'):
                parts = text.split(maxsplit=1)
                qr_group = parts[1].strip() if len(parts) > 1 else None
                response = await admin_handler.handle_list_qr_groups(chat_id, qr_group=qr_group)
                await event.respond(response)

            elif text.startswith('/admin_set_qr_group'):
                parts = text.split(maxsplit=1)
                if len(parts) > 1:
                    is_admin, error = admin_handler.verify_access(chat_id)
                    if not is_admin:
                        await event.respond(error)
                    else:
                        qr_group = parts[1].strip()
                        qr_import_sessions[sender_id] = {"chat_id": chat_id, "qr_group": qr_group}
                        user_import_sessions.pop(sender_id, None)
                        await event.respond(
                            f"📷 Forward the original GroupHelp QR image message for `{qr_group}` here.\n\n"
                            "It must be a forwarded image message with `.importbackup` as its caption/body. "
                            "Send `!cancel` to abort."
                        )
                else:
                    await event.respond("❌ Usage: `/admin_set_qr_group <qr_group>`")
            
            elif text.startswith('/admin_set_qr'):
                parts = text.split(maxsplit=2)
                if len(parts) > 1:
                    if len(parts) > 2:
                        qr_group = parts[1].strip()
                        qr_data = parts[2].strip()
                    else:
                        qr_group = DEFAULT_QR_GROUP
                        qr_data = parts[1].strip()
                    response = await admin_handler.handle_set_qr_backup(chat_id, qr_data, qr_group=qr_group)
                    qr_import_sessions.pop(sender_id, None)
                    user_import_sessions.pop(sender_id, None)
                    await event.respond(response)
                else:
                    is_admin, error = admin_handler.verify_access(chat_id)
                    if not is_admin:
                        await event.respond(error)
                    else:
                        qr_import_sessions[sender_id] = {"chat_id": chat_id, "qr_group": DEFAULT_QR_GROUP}
                        user_import_sessions.pop(sender_id, None)
                        await event.respond(
                            "📷 Forward the original GroupHelp QR image message for `default` here.\n\n"
                            "It must be a forwarded image message with `.importbackup` as its caption/body. "
                            "Send `!cancel` to abort."
                        )
            
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
• `/admin_set_users <id_or_username_or_id:username> ...` - Set default users
• `/admin_add_users <id_or_username_or_id:username> ...` - Add users to default list
• `/admin_add_users` - Add a forwarded user to default list
• `/admin_remove_users <id_or_username_or_id:username> ...` - Remove users from default list
• `/admin_add_user <username_or_id:username>` - Add new user to database
• `/admin_add_user` - Add a forwarded user to database
• `/admin_get_qr [qr_group]` - Get QR backup data
• `/admin_set_qr [qr_group] <qr_payload>` - Set QR backup data directly
• `/admin_set_qr` - Decode a forwarded `.importbackup` QR image for `default`
• `/admin_set_qr_group <qr_group>` - Decode a forwarded `.importbackup` QR image for a QR group
• `/admin_qr_groups [qr_group]` - List QR groups and assignments
• `/admin_qr_group_add <qr_group> <telegram_group_id> ...` - Assign groups to QR config
• `/admin_qr_group_remove <telegram_group_id> ...` - Remove QR assignments
• `/admin_sync_qr [qr_group|all]` - Send stored `.importbackup` QR to owned assigned groups
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
        if staff_chat_id:
            await client.send_message(staff_chat_id, "GroupFactory Service Userbot started.")

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
