import os
import logging
import traceback
from datetime import datetime
import discord
from discord.ext import commands
import asyncio
import threading

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)

class _DiscordBotManager:
    """Internal class to manage Discord bot state without globals"""
    def __init__(self):
        self.bot = None
        self.error_channel = None
        self.inbox_channel = None
        self.error_queue = asyncio.Queue()
        self.contact_queue = asyncio.Queue()
        self.loop = None
        self.loop_thread = None

    def _get_loop(self):
        if self.loop is None:
            logger.info("Creating new Discord event loop")
            self.loop = asyncio.new_event_loop()
            if not self.loop_thread or not self.loop_thread.is_alive():
                def run_loop(loop):
                    asyncio.set_event_loop(loop)
                    loop.run_forever()
                self.loop_thread = threading.Thread(target=run_loop, args=(self.loop,), daemon=True)
                self.loop_thread.start()
                logger.info("Started Discord event loop thread")
        return self.loop

    def setup(self):
        discord_token = os.environ.get("DISCORD_TOKEN")
        channel_id = os.environ.get("DISCORD_CHANNEL_ID")
        inbox_channel_id = os.environ.get("DISCORD_INBOX_CHANNEL_ID")

        if not discord_token:
            logger.warning("DISCORD_TOKEN not found in environment variables. Discord bot will not be started.")
            return None

        intents = discord.Intents.default()
        intents.message_content = False
        self.bot = commands.Bot(command_prefix="!", intents=intents)

        @self.bot.event
        async def on_ready():
            logger.info(f"Logged in as {self.bot.user.name} ({self.bot.user.id})")
            if channel_id:
                try:
                    self.error_channel = self.bot.get_channel(int(channel_id)) or await self.bot.fetch_channel(int(channel_id))
                    logger.info(f"Error channel set to: {self.error_channel.name} (ID: {self.error_channel.id})")
                    await self.error_channel.send(embed=discord.Embed(
                        title="📢 Error Monitoring Bot Connected",
                        description="Error monitor is online.",
                        color=0x2ecc71,
                        timestamp=datetime.now()
                    ).set_footer(text="Error Monitor").set_thumbnail(url="https://cdn.discordapp.com/emojis/736613075517603911.png?size=96"))
                except Exception as e:
                    logger.error(f"Failed to get error channel: {str(e)}\n{traceback.format_exc()}")

            if inbox_channel_id:
                try:
                    self.inbox_channel = self.bot.get_channel(int(inbox_channel_id)) or await self.bot.fetch_channel(int(inbox_channel_id))
                    logger.info(f"Inbox channel set to: {self.inbox_channel.name} (ID: {self.inbox_channel.id})")
                    await self.inbox_channel.send(embed=discord.Embed(
                        title="📬 Contact Form Bot Connected",
                        description="Contact form system is online.",
                        color=0x3498db,
                        timestamp=datetime.now()
                    ).set_footer(text="Inbox Channel").set_thumbnail(url="https://cdn.discordapp.com/emojis/736613075517603911.png?size=96"))
                except Exception as e:
                    logger.error(f"Failed to find inbox channel: {str(e)}\n{traceback.format_exc()}")
            else:
                logger.warning("DISCORD_INBOX_CHANNEL_ID not set. Searching for 'inbox'.")
                for guild in self.bot.guilds:
                    for channel in guild.channels:
                        if channel.name == 'inbox' and str(channel.type) == 'text':
                            self.inbox_channel = channel
                            logger.info(f"Inbox channel found: {self.inbox_channel.name} (ID: {self.inbox_channel.id})")
                            break
                    if self.inbox_channel:
                        break
                if not self.inbox_channel:
                    logger.warning("No 'inbox' channel found.")

            asyncio.create_task(self._process_error_queue())
            asyncio.create_task(self._process_contact_queue())

        threading.Thread(target=self._run_bot, args=(discord_token,), daemon=True).start()
        return self.bot

    def _run_bot(self, token):
        try:
            future = asyncio.run_coroutine_threadsafe(self.bot.start(token), self._get_loop())
            future.result()
        except Exception as e:
            logger.error(f"Failed to start Discord bot: {str(e)}\n{traceback.format_exc()}")

    async def _process_error_queue(self):
        while True:
            try:
                error_data = await asyncio.wait_for(self.error_queue.get(), timeout=1.0)
                if self.error_channel:
                    await self.error_channel.send(embed=self._create_error_embed(error_data))
                    logger.info(f"Sent error to Discord: {error_data['error_type']}")
                self.error_queue.task_done()
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                logger.error(f"Error processing error queue: {str(e)}\n{traceback.format_exc()}")
            await asyncio.sleep(0.1)

    async def _process_contact_queue(self):
        while True:
            try:
                contact_data = await asyncio.wait_for(self.contact_queue.get(), timeout=1.0)
                if self.inbox_channel:
                    await self.inbox_channel.send(embed=self._create_contact_embed(contact_data))
                    logger.info("Sent contact form submission to Discord")
                self.contact_queue.task_done()
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                logger.error(f"Error processing contact queue: {str(e)}\n{traceback.format_exc()}")
            await asyncio.sleep(0.1)

    def _create_error_embed(self, error_data):
        embed = discord.Embed(
            title=f"⚠️ Error Detected: {error_data['error_type']}",
            description=f"**{error_data['message']}**",
            color=0xe74c3c,
            timestamp=datetime.now()
        )
        embed.add_field(name="🔍 Request Details", value=f"**Route:** `{error_data['route']}`\n**Method:** `{error_data['method']}`\n**Status:** `{error_data['status_code']}`", inline=False)
        if 'user_agent' in error_data:
            embed.add_field(name="🌐 User Agent", value=f"`{error_data['user_agent']}`", inline=False)
        if error_data.get('traceback'):
            traceback_str = error_data['traceback'][:997] + "..." if len(error_data['traceback']) > 1000 else error_data['traceback']
            embed.add_field(name="📋 Traceback", value=f"```python\n{traceback_str}\n```", inline=False)
        embed.set_footer(text=f"Error Monitor • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/585763004068839424.png?size=96")
        return embed

    def _create_contact_embed(self, contact_data):
        embed = discord.Embed(
            title="📬 New Contact Form Submission",
            description=f"**{contact_data['subject']}**\n\n{contact_data['message']}",
            color=0x2ecc71,
            timestamp=datetime.now()
        )
        embed.add_field(name="👤 From", value=f"**{contact_data['name']}**", inline=True)
        embed.add_field(name="📧 Email", value=f"[{contact_data['email']}](mailto:{contact_data['email']})", inline=True)
        embed.set_footer(text=f"Contact Form • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/736613075517603911.png?size=96")
        return embed

# Singleton instance
_manager = _DiscordBotManager()

# Public API functions (same as original)
def setup_discord_bot():
    """Initialize and setup the Discord bot"""
    return _manager.setup()

def send_error_to_discord(error_info):
    """Add error to the queue for processing"""
    if not _manager.bot:
        logger.warning("Discord bot not initialized")
        return
    if not _manager.bot.is_ready():
        logger.warning("Discord bot not yet ready")
        return
    if not _manager.error_channel:
        logger.warning("Discord channel not available")
        return
    loop = _manager._get_loop()
    asyncio.run_coroutine_threadsafe(_manager.error_queue.put(error_info), loop)
    logger.info(f"Queued error: {error_info['error_type']}")

def send_contact_to_discord(contact_info):
    """Add contact form data to the queue for processing"""
    if not _manager.bot:
        logger.warning("Discord bot not initialized")
        return
    if not _manager.bot.is_ready():
        logger.warning("Discord bot not yet ready")
        return
    if not _manager.inbox_channel:
        logger.warning("Inbox channel not available")
        return
    loop = _manager._get_loop()
    asyncio.run_coroutine_threadsafe(_manager.contact_queue.put(contact_info), loop)
    logger.info("Queued contact form submission")
