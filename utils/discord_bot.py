import os
import logging
from datetime import datetime
import discord
import asyncio
import threading
import httpx

# Configure logging - minimal output
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Show only INFO and above (no DEBUG)

# Suppress Discord library logs unless they’re ERROR or higher
for logger_name in ['discord', 'discord.http']:
    discord_logger = logging.getLogger(logger_name)
    discord_logger.setLevel(logging.ERROR)

# Global variables
http_client = None
error_channel_id = None
inbox_channel_id = None
error_queue = None
contact_queue = None
_bot_initialized = False  # Flag to prevent multiple initializations
_discord_loop = None
_discord_loop_thread = None

def _get_discord_loop():
    """Get or create the shared Discord event loop"""
    global _discord_loop, _discord_loop_thread
    if _discord_loop is None:
        _discord_loop = asyncio.new_event_loop()
        def run_loop(loop):
            asyncio.set_event_loop(loop)
            loop.run_forever()
        _discord_loop_thread = threading.Thread(target=run_loop, args=(_discord_loop,), daemon=True)
        _discord_loop_thread.start()
        logger.info("Started Discord event loop thread")
    return _discord_loop

def setup_discord_bot():
    """Initialize and setup the Discord bot only once"""
    global http_client, error_channel_id, inbox_channel_id, error_queue, contact_queue, _bot_initialized
    if _bot_initialized:
        logger.info("Discord bot already initialized, skipping setup")
        return http_client

    discord_token = os.environ.get("DISCORD_TOKEN")
    error_channel_id = os.environ.get("DISCORD_CHANNEL_ID")
    inbox_channel_id = os.environ.get("DISCORD_INBOX_CHANNEL_ID")

    if not discord_token:
        logger.warning("DISCORD_TOKEN not found, Discord bot disabled")
        return None

    http_client = httpx.AsyncClient()
    # Initialize queues only once
    error_queue = asyncio.Queue()
    contact_queue = asyncio.Queue()

    async def send_initial_messages():
        if error_channel_id:
            embed = discord.Embed(
                title="📢 Error Monitoring Bot Connected",
                description="SoftTouch error monitor is now online.",
                color=0x2ecc71,
                timestamp=datetime.now()
            ).set_footer(text="Error Monitor").set_thumbnail(url="https://cdn.discordapp.com/emojis/736613075517603911.png?size=96")
            await send_embed_to_channel(error_channel_id, embed, discord_token)
            logger.info(f"Error channel set: {error_channel_id}")
        else:
            logger.warning("Error channel not found")

        if inbox_channel_id:
            embed = discord.Embed(
                title="📬 Contact Bot Connected",
                description="SoftTouch contact form system is now online.",
                color=0x3498db,
                timestamp=datetime.now()
            ).set_footer(text="Inbox Channel").set_thumbnail(url="https://cdn.discordapp.com/emojis/736613075517603911.png?size=96")
            await send_embed_to_channel(inbox_channel_id, embed, discord_token)
            logger.info(f"Inbox channel set: {inbox_channel_id}")
        else:
            logger.warning("Inbox channel not found")

    async def process_error_queue():
        while True:
            try:
                error_data = await asyncio.wait_for(error_queue.get(), timeout=1.0)
                if error_channel_id:
                    embed = create_error_embed(error_data)
                    await send_embed_to_channel(error_channel_id, embed, discord_token)
                error_queue.task_done()
            except asyncio.TimeoutError:
                await asyncio.sleep(0.1)

    async def process_contact_queue():
        while True:
            try:
                contact_data = await asyncio.wait_for(contact_queue.get(), timeout=1.0)
                if inbox_channel_id:
                    embed = create_contact_embed(contact_data)
                    await send_embed_to_channel(inbox_channel_id, embed, discord_token)
                contact_queue.task_done()
            except asyncio.TimeoutError:
                await asyncio.sleep(0.1)

    def run_initial_setup():
        loop = _get_discord_loop()
        asyncio.run_coroutine_threadsafe(send_initial_messages(), loop)
        asyncio.run_coroutine_threadsafe(process_error_queue(), loop)
        asyncio.run_coroutine_threadsafe(process_contact_queue(), loop)

    setup_thread = threading.Thread(target=run_initial_setup, daemon=True)
    setup_thread.start()
    _bot_initialized = True
    logger.info("Discord bot initialized")
    return http_client

async def send_embed_to_channel(channel_id, embed, token):
    """Send an embed to a Discord channel using HTTP"""
    async with httpx.AsyncClient() as client:
        payload = {
            "embeds": [embed.to_dict()]
        }
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
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to send message to channel {channel_id}: {e}")

def create_error_embed(error_data):
    embed = discord.Embed(
        title=f"⚠️ Error: {error_data['error_type']}",
        description=f"**{error_data['message']}**",
        color=0xe74c3c,
        timestamp=datetime.now()
    )
    embed.add_field(name="🔍 Request", value=f"Route: `{error_data['route']}`\nMethod: `{error_data['method']}`\nStatus: `{error_data['status_code']}`", inline=False)
    if 'user_agent' in error_data:
        embed.add_field(name="🌐 User Agent", value=f"`{error_data['user_agent']}`", inline=False)
    if error_data.get('traceback'):
        traceback_str = error_data['traceback'][:997] + "..." if len(error_data['traceback']) > 1000 else error_data['traceback']
        embed.add_field(name="📋 Traceback", value=f"```python\n{traceback_str}\n```", inline=False)
    embed.set_footer(text="Error Monitor")
    embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/585763004068839424.png?size=96")
    return embed

def create_contact_embed(contact_data):
    embed = discord.Embed(
        title=f"📬 New Form: {contact_data['subject']}",
        description=contact_data['message'],
        color=0x2ecc71,
        timestamp=datetime.now()
    )
    embed.add_field(name="👤 From", value=f"**{contact_data['name']}**", inline=True)
    embed.add_field(name="📧 Email", value=f"[{contact_data['email']}](mailto:{contact_data['email']})", inline=True)
    embed.set_footer(text="Contact Form")
    embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/736613075517603911.png?size=96")
    return embed

def send_error_to_discord(error_info):
    if not http_client or not error_channel_id or not error_queue:
        logger.warning("Discord bot or channel not ready for error reporting")
        return
    loop = _get_discord_loop()
    asyncio.run_coroutine_threadsafe(error_queue.put(error_info), loop)

def send_contact_to_discord(contact_info):
    if not http_client or not inbox_channel_id or not contact_queue:
        logger.warning("Discord bot or channel not ready for contact reporting")
        return
    loop = _get_discord_loop()
    asyncio.run_coroutine_threadsafe(contact_queue.put(contact_info), loop)
