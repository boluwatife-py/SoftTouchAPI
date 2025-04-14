import os
import logging
from datetime import datetime
import discord
import asyncio
import threading

# Configure logging - minimal output
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Show only INFO and above (no DEBUG)

# Suppress Discord library logs unless they’re ERROR or higher
for logger_name in ['discord', 'discord.http', 'discord.gateway', 'discord.client']:
    discord_logger = logging.getLogger(logger_name)
    discord_logger.setLevel(logging.ERROR)

# Global variables
discord_bot = None
error_channel = None
inbox_channel = None
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
    global discord_bot, error_channel, inbox_channel, error_queue, contact_queue, _bot_initialized
    if _bot_initialized:
        logger.info("Discord bot already initialized, skipping setup")
        return discord_bot

    discord_token = os.environ.get("DISCORD_TOKEN")
    channel_id = os.environ.get("DISCORD_CHANNEL_ID")
    inbox_channel_id = os.environ.get("DISCORD_INBOX_CHANNEL_ID")

    if not discord_token:
        logger.warning("DISCORD_TOKEN not found, Discord bot disabled")
        return None

    intents = discord.Intents.none()
    intents.guilds = True
    intents.guild_messages = True
    discord_bot = discord.Client(intents=intents)

    # Initialize queues only once
    error_queue = asyncio.Queue()
    contact_queue = asyncio.Queue()

    @discord_bot.event
    async def on_ready():
        global error_channel, inbox_channel
        logger.info(f"Logged in as {discord_bot.user.name} ({discord_bot.user.id})")

        # Set error channel
        if channel_id:
            error_channel = discord_bot.get_channel(int(channel_id)) or await discord_bot.fetch_channel(int(channel_id))
            if error_channel:
                logger.info(f"Error channel set: {error_channel.name}")
                await error_channel.send(embed=discord.Embed(
                    title="📢 Error Monitoring Bot Connected",
                    description="SoftTouch error monitor is now online.",
                    color=0x2ecc71,
                    timestamp=datetime.now()
                ).set_footer(text="Error Monitor").set_thumbnail(url="https://cdn.discordapp.com/emojis/736613075517603911.png?size=96"))
            else:
                logger.warning("Error channel not found")

        # Set inbox channel
        if inbox_channel_id:
            inbox_channel = discord_bot.get_channel(int(inbox_channel_id)) or await discord_bot.fetch_channel(int(inbox_channel_id))
            if inbox_channel:
                logger.info(f"Inbox channel set: {inbox_channel.name}")
                await inbox_channel.send(embed=discord.Embed(
                    title="📬 Contact Bot Connected",
                    description="SoftTouch contact form system is now online.",
                    color=0x3498db,
                    timestamp=datetime.now()
                ).set_footer(text="Inbox Channel").set_thumbnail(url="https://cdn.discordapp.com/emojis/736613075517603911.png?size=96"))
            else:
                logger.warning("Inbox channel not found")

        # Start queue processors
        asyncio.create_task(process_error_queue())
        asyncio.create_task(process_contact_queue())

    async def process_error_queue():
        while True:
            try:
                error_data = await asyncio.wait_for(error_queue.get(), timeout=1.0)
                if error_channel:
                    await error_channel.send(embed=create_error_embed(error_data))
                error_queue.task_done()
            except asyncio.TimeoutError:
                await asyncio.sleep(0.1)

    async def process_contact_queue():
        while True:
            try:
                contact_data = await asyncio.wait_for(contact_queue.get(), timeout=1.0)
                if inbox_channel:
                    await inbox_channel.send(embed=create_contact_embed(contact_data))
                contact_queue.task_done()
            except asyncio.TimeoutError:
                await asyncio.sleep(0.1)

    def run_discord_bot():
        loop = _get_discord_loop()
        future = asyncio.run_coroutine_threadsafe(discord_bot.start(discord_token), loop)
        future.add_done_callback(lambda fut: logger.error(f"Discord bot error: {fut.exception()}", exc_info=True) if fut.exception() else None)

    bot_thread = threading.Thread(target=run_discord_bot, daemon=True)
    bot_thread.start()
    _bot_initialized = True
    logger.info("Discord bot initialized")
    return discord_bot

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
    if not discord_bot or not error_channel or not error_queue:
        logger.warning("Discord bot or channel not ready for error reporting")
        return
    loop = _get_discord_loop()
    asyncio.run_coroutine_threadsafe(error_queue.put(error_info), loop)

def send_contact_to_discord(contact_info):
    if not discord_bot or not inbox_channel or not contact_queue:
        logger.warning("Discord bot or channel not ready for contact reporting")
        return
    loop = _get_discord_loop()
    asyncio.run_coroutine_threadsafe(contact_queue.put(contact_info), loop)