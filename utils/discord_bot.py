import os
import logging
from datetime import datetime
import httpx
import asyncio
import threading

# Configure logging - detailed output for debugging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
file_handler = logging.FileHandler("discord_bot.log")
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)
logger.addHandler(console_handler)
logger.addHandler(file_handler)

# Global variables
http_client = None
error_channel_id = None
inbox_channel_id = None
error_queue = None
contact_queue = None
_bot_initialized = False

def setup_discord_bot():
    """Initialize and setup the Discord bot only once"""
    global http_client, error_channel_id, inbox_channel_id, error_queue, contact_queue, _bot_initialized
    if _bot_initialized:
        logger.info("Discord bot already initialized, skipping setup")
        return http_client

    discord_token = os.environ.get("DISCORD_TOKEN")
    error_channel_id = os.environ.get("DISCORD_CHANNEL_ID")
    inbox_channel_id = os.environ.get("DISCORD_INBOX_CHANNEL_ID")

    # Debug environment variables
    logger.debug(f"Environment variables - DISCORD_TOKEN: {'set' if discord_token else 'not set'}, "
                 f"ERROR_CHANNEL_ID: {error_channel_id}, INBOX_CHANNEL_ID: {inbox_channel_id}")

    if not discord_token:
        logger.warning("DISCORD_TOKEN not found, Discord bot disabled")
        return None

    http_client = httpx.AsyncClient()
    error_queue = asyncio.Queue()
    contact_queue = asyncio.Queue()
    _bot_initialized = True

    # Log initial state
    logger.info("Discord bot initialized")
    logger.debug(f"Bot state - http_client: {http_client}, error_queue: {error_queue}, "
                 f"contact_queue: {contact_queue}, bot_initialized: {_bot_initialized}")

    # Start queue processing in a separate thread
    def run_queue_processing():
        logger.debug("Starting queue processing thread")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def process_queues():
            while True:
                try:
                    logger.debug("Queue processing loop running")
                    # Process error queue
                    if error_channel_id:
                        try:
                            error_data = await asyncio.wait_for(error_queue.get(), timeout=1.0)
                            logger.debug(f"Processing error queue item: {error_data}")
                            await send_error_embed(error_channel_id, error_data, discord_token)
                            error_queue.task_done()
                            logger.debug("Error queue item processed")
                        except asyncio.TimeoutError:
                            pass

                    # Process contact queue
                    if inbox_channel_id:
                        try:
                            contact_data = await asyncio.wait_for(contact_queue.get(), timeout=1.0)
                            logger.debug(f"Processing contact queue item: {contact_data}")
                            await send_contact_embed(inbox_channel_id, contact_data, discord_token)
                            contact_queue.task_done()
                            logger.debug("Contact queue item processed")
                        except asyncio.TimeoutError:
                            pass

                    await asyncio.sleep(0.1)
                except Exception as e:
                    logger.error(f"Error in queue processing: {e}", exc_info=True)
                    await asyncio.sleep(1.0)

        loop.run_until_complete(process_queues())

    logger.info("Starting queue processing thread")
    threading.Thread(target=run_queue_processing, daemon=True).start()
    return http_client

async def send_error_embed(channel_id, error_data, token):
    """Send an error embed to a Discord channel"""
    logger.debug(f"Preparing error embed for channel {channel_id}: {error_data}")
    embed = {
        "title": f"⚠️ Error: {error_data['error_type']}",
        "description": f"**{error_data['message']}**",
        "color": 0xe74c3c,
        "timestamp": datetime.now().isoformat(),
        "footer": {"text": "Error Monitor"},
        "thumbnail": {"url": "https://cdn.discordapp.com/emojis/585763004068839424.png?size=96"},
        "fields": [
            {
                "name": "🔍 Request",
                "value": f"Route: `{error_data['route']}`\nMethod: `{error_data['method']}`\nStatus: `{error_data['status_code']}`",
                "inline": False
            }
        ]
    }
    if 'user_agent' in error_data:
        embed["fields"].append({
            "name": "🌐 User Agent",
            "value": f"`{error_data['user_agent']}`",
            "inline": False
        })
    if error_data.get('traceback'):
        traceback_str = error_data['traceback'][:997] + "..." if len(error_data['traceback']) > 1000 else error_data['traceback']
        embed["fields"].append({
            "name": "📋 Traceback",
            "value": f"```python\n{traceback_str}\n```",
            "inline": False
        })

    await send_embed_to_channel(channel_id, embed, token)

async def send_contact_embed(channel_id, contact_data, token):
    """Send a contact embed to a Discord channel"""
    logger.debug(f"Preparing contact embed for channel {channel_id}: {contact_data}")
    embed = {
        "title": f"📬 New Form: {contact_data['subject']}",
        "description": contact_data['message'],
        "color": 0x2ecc71,
        "timestamp": datetime.now().isoformat(),
        "footer": {"text": "Contact Form"},
        "thumbnail": {"url": "https://cdn.discordapp.com/emojis/736613075517603911.png?size=96"},
        "fields": [
            {"name": "👤 From", "value": f"**{contact_data['name']}**", "inline": True},
            {"name": "📧 Email", "value": f"[{contact_data['email']}](mailto:{contact_data['email']})", "inline": True}
        ]
    }
    await send_embed_to_channel(channel_id, embed, token)

async def send_embed_to_channel(channel_id, embed, token):
    """Send an embed to a Discord channel using HTTP"""
    logger.debug(f"Sending embed to channel {channel_id}")
    async with httpx.AsyncClient() as client:
        payload = {"embeds": [embed]}
        headers = {
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json"
        }
        try:
            response = await client.post(
                f"https://discord.com/api/v10/channels/{channel_id}/messages",
                json=payload,
                headers=headers
            )
            logger.debug(f"Discord API response: {response.status_code} - {response.text}")
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to send message to channel {channel_id}: {e}, Response: {e.response.text}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error sending message to channel {channel_id}: {e}", exc_info=True)

def send_error_to_discord(error_info):
    """Queue an error message to be sent to Discord"""
    logger.debug(f"Queueing error message: {error_info}")
    if not http_client or not error_channel_id or not error_queue:
        logger.warning(f"Discord bot not ready for error reporting - "
                       f"http_client: {http_client}, error_channel_id: {error_channel_id}, error_queue: {error_queue}")
        return
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    asyncio.run(error_queue.put(error_info))
    logger.debug("Error message queued")

def send_contact_to_discord(contact_info):
    """Queue a contact message to be sent to Discord"""
    logger.debug(f"Queueing contact message: {contact_info}")
    if not http_client or not inbox_channel_id or not contact_queue:
        logger.warning(f"Discord bot not ready for contact reporting - "
                       f"http_client: {http_client}, inbox_channel_id: {inbox_channel_id}, contact_queue: {contact_queue}")
        return
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    asyncio.run(contact_queue.put(contact_info))
    logger.debug("Contact message queued")