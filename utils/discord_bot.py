import os
import logging
import traceback
from datetime import datetime
import discord
from discord.ext import commands
import asyncio
import threading

# Configure logging - suppress all error messages for Discord-related operations
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)

# Create a custom filter to suppress error messages
class SuppressErrorFilter(logging.Filter):
    def filter(self, record):
        return record.levelno < logging.ERROR  # Only allow records below ERROR level

# Add the filter to the logger
logger.addFilter(SuppressErrorFilter())

# Also configure discord.py's loggers to not show errors to console
for logger_name in ['discord', 'discord.http', 'discord.gateway', 'discord.client']:
    discord_logger = logging.getLogger(logger_name)
    discord_logger.addFilter(SuppressErrorFilter())

# Global variables
discord_bot = None  # The discord.py bot instance
error_channel = None  # The channel where errors will be sent
inbox_channel = None  # The channel where contact form submissions will be sent
error_queue = asyncio.Queue()  # Queue for storing errors to be sent
contact_queue = asyncio.Queue()  # Queue for storing contact form submissions

# Create shared event loop for all Discord operations
_discord_loop = None  # Shared event loop
_discord_loop_thread = None  # Thread running the event loop

def _get_discord_loop():
    """Get the shared Discord event loop"""
    global _discord_loop, _discord_loop_thread
    
    if _discord_loop is None:
        logger.info("Creating new Discord event loop")
        _discord_loop = asyncio.new_event_loop()
        
        # Start loop in separate thread if it's not running
        if not _discord_loop_thread or not _discord_loop_thread.is_alive():
            def run_loop(loop):
                asyncio.set_event_loop(loop)
                loop.run_forever()
                
            _discord_loop_thread = threading.Thread(target=run_loop, args=(_discord_loop,), daemon=True)
            _discord_loop_thread.start()
            logger.info("Started Discord event loop thread")
            
    return _discord_loop

def setup_discord_bot():
    """Initialize and setup the Discord bot"""
    global discord_bot, client
    
    # Get Discord token from environment
    discord_token = os.environ.get("DISCORD_TOKEN")
    channel_id = os.environ.get("DISCORD_CHANNEL_ID")
    inbox_channel_id = os.environ.get("DISCORD_INBOX_CHANNEL_ID")
    
    if not discord_token:
        logger.warning("DISCORD_TOKEN not found in environment variables. Discord bot will not be started.")
        return None
    
    # Set intents for the bot - only use non-privileged intents
    intents = discord.Intents.none()  # Start with no intents
    # Add only the intents we need
    intents.guilds = True  # Need access to guilds to find channels
    intents.guild_messages = True  # Need to send messages to guild channels
    
    # Create a client instance instead of a bot, since we don't need commands
    discord_bot = discord.Client(intents=intents)
    
    @discord_bot.event
    async def on_ready():
        """Event triggered when the bot is ready"""
        global error_channel, inbox_channel
        logger.info(f"Logged in as {discord_bot.user.name} ({discord_bot.user.id})")
        
        # Get the error reporting channel
        try:
            if channel_id:
                # Try to get the error channel by ID
                error_channel = discord_bot.get_channel(int(channel_id))
                
                # If not found, try fetching it
                if not error_channel:
                    error_channel = await discord_bot.fetch_channel(int(channel_id))
                    
                logger.info(f"Error channel set to: {error_channel.name} (ID: {error_channel.id})")
            else:
                # If no ID provided, try to find by name
                logger.warning("DISCORD_CHANNEL_ID not set. Attempting to find channel by name 'errors' or 'error-logs'.")
                for guild in discord_bot.guilds:
                    for channel in guild.channels:
                        if channel.name in ['errors', 'error-logs', 'logs'] and str(channel.type) == 'text':
                            error_channel = channel
                            logger.info(f"Error channel found by name: {error_channel.name} (ID: {error_channel.id})")
                            break
                    if error_channel:
                        break
                        
            # Send test message if channel found
            if error_channel:
                # Test send a message to verify permissions
                test_embed = discord.Embed(
                    title="📢 Error Monitoring Bot Connected",
                    description="The Flask application error monitor is now online and ready to report errors.",
                    color=0x2ecc71  # Green color
                )
                test_embed.add_field(
                    name="Channel Configuration", 
                    value="✅ This channel is now configured to receive error notifications from your application.", 
                    inline=False
                )
                test_embed.set_footer(text=f"Error Monitor • Initialized at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                test_embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/736613075517603911.png?size=96")
                
                await error_channel.send(embed=test_embed)
                logger.info("Successfully sent test message to Discord channel")
            else:
                logger.warning("No suitable error channel found. Error notifications will be disabled.")
                
        except Exception as e:
            logger.error(f"Failed to get error channel: {str(e)}\n{traceback.format_exc()}")
        
        # Get the inbox channel either by ID or by name
        try:
            if inbox_channel_id:
                # Try to get the inbox channel by ID first
                inbox_channel = discord_bot.get_channel(int(inbox_channel_id))
                
                # If not found, try fetching it
                if not inbox_channel:
                    inbox_channel = await discord_bot.fetch_channel(int(inbox_channel_id))
                    
                logger.info(f"Inbox channel set to: {inbox_channel.name} (ID: {inbox_channel.id})")
                
                # Test send a message to verify permissions
                test_embed = discord.Embed(
                    title="📬 Contact Form Bot Connected",
                    description="The Flask application contact form system is now online and ready to receive submissions.",
                    color=0x3498db  # Nice blue color
                )
                test_embed.add_field(
                    name="Channel Configuration", 
                    value="✅ This channel is now configured to receive contact form submissions.", 
                    inline=False
                )
                test_embed.set_footer(text=f"Inbox Channel • Initialized at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                test_embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/736613075517603911.png?size=96")
                
                await inbox_channel.send(embed=test_embed)
                logger.info("Successfully sent test message to inbox channel")
            else:
                # If no ID provided, try to find by name
                logger.warning("DISCORD_INBOX_CHANNEL_ID not set. Attempting to find channel by name 'inbox'.")
                for guild in discord_bot.guilds:
                    for channel in guild.channels:
                        if channel.name == 'inbox' and str(channel.type) == 'text':
                            inbox_channel = channel
                            logger.info(f"Inbox channel found by name: {inbox_channel.name} (ID: {inbox_channel.id})")
                            break
                
                if not inbox_channel:
                    logger.warning("No channel named 'inbox' found. Contact form submissions will not be reported. Please set DISCORD_INBOX_CHANNEL_ID.")
        except Exception as e:
            logger.error(f"Failed to find inbox channel: {str(e)}\n{traceback.format_exc()}")
        
        # Start the processing tasks in the current event loop
        asyncio.create_task(process_error_queue())
        asyncio.create_task(process_contact_queue())
    
    async def process_error_queue():
        """Process errors from the queue and send them to Discord"""
        global error_channel
        logger.info("Starting error queue processor task")
        
        while True:
            try:
                # Log queue status for debugging
                if not error_queue.empty():
                    logger.debug(f"Items in error queue: approximately {error_queue.qsize()}")
                
                # Get an error from the queue with a timeout
                try:
                    error_data = await asyncio.wait_for(error_queue.get(), timeout=1.0)
                    logger.debug(f"Retrieved error from queue: {error_data['error_type']}")
                    
                    # Make sure we have a channel to send to
                    if error_channel:
                        logger.debug(f"Sending error to channel: {error_channel.name}")
                        embed = create_error_embed(error_data)
                        await error_channel.send(embed=embed)
                        logger.info(f"Successfully sent error to Discord: {error_data['error_type']}")
                    else:
                        logger.error("Error channel not available for sending")
                        
                    # Mark task as done
                    error_queue.task_done()
                except asyncio.TimeoutError:
                    # This is normal, just continue
                    pass
            except Exception as e:
                logger.error(f"Error processing Discord error queue: {str(e)}\n{traceback.format_exc()}")
            
            # Short sleep to prevent CPU spinning
            await asyncio.sleep(0.1)
            
    async def process_contact_queue():
        """Process contact form submissions from the queue and send them to Discord"""
        global inbox_channel
        logger.info("Starting contact form queue processor task")
        
        while True:
            try:
                # Get a contact form submission from the queue with a timeout
                try:
                    contact_data = await asyncio.wait_for(contact_queue.get(), timeout=1.0)
                    
                    # Make sure we have a channel to send to
                    if inbox_channel:
                        embed = create_contact_embed(contact_data)
                        await inbox_channel.send(embed=embed)
                        logger.info("Successfully sent contact form submission to Discord inbox")
                    else:
                        logger.error("Inbox channel not available for sending contact form")
                        
                    # Mark task as done
                    contact_queue.task_done()
                except asyncio.TimeoutError:
                    # This is normal, just continue
                    pass
            except Exception as e:
                logger.error(f"Error processing Discord contact queue: {str(e)}\n{traceback.format_exc()}")
            
            # Short sleep to prevent CPU spinning
            await asyncio.sleep(0.1)
    
    # Start the bot in a separate thread
    def run_discord_bot():
        """Run the Discord bot in a separate thread"""
        try:
            # Use our shared event loop
            loop = _get_discord_loop()
            
            # Run the bot
            future = asyncio.run_coroutine_threadsafe(discord_bot.start(discord_token), loop)
            logger.info("Discord bot start coroutine scheduled")
            
            # Add error handling
            def on_done(fut):
                try:
                    fut.result()  # This will raise any exceptions that occurred
                except Exception as e:
                    logger.error(f"Discord bot terminated with error: {str(e)}\n{traceback.format_exc()}")
                    
            future.add_done_callback(on_done)
        except Exception as e:
            logger.error(f"Failed to start Discord bot: {str(e)}\n{traceback.format_exc()}")
    
    # Start the bot on a separate thread
    bot_thread = threading.Thread(target=run_discord_bot, daemon=True)
    bot_thread.start()
    
    logger.info("Discord bot initialized and started")
    return discord_bot

def create_error_embed(error_data):
    """Create a Discord embed for error reporting"""
    # Create a visually appealing error embed with rich formatting
    embed = discord.Embed(
        title=f"⚠️ Error Detected: {error_data['error_type']}",
        description=f"**{error_data['message']}**",
        color=0xe74c3c,  # Red color for errors
        timestamp=datetime.now()
    )
    
    # Add request information
    embed.add_field(
        name="🔍 Request Details",
        value=f"**Route:** `{error_data['route']}`\n**Method:** `{error_data['method']}`\n**Status:** `{error_data['status_code']}`",
        inline=False
    )
    
    # Add user agent if available
    if 'user_agent' in error_data:
        embed.add_field(
            name="🌐 User Agent",
            value=f"`{error_data['user_agent']}`",
            inline=False
        )
    
    # Add traceback with proper formatting
    if error_data.get('traceback'):
        # Truncate traceback to fit in Discord embed (max 1024 chars per field)
        traceback_str = error_data['traceback']
        if len(traceback_str) > 1000:
            traceback_str = traceback_str[:997] + "..."
        
        embed.add_field(
            name="📋 Traceback",
            value=f"```python\n{traceback_str}\n```",
            inline=False
        )
    
    # Add metadata
    current_time = datetime.now()
    embed.set_footer(
        text=f"Error Monitor • {current_time.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    # Add a thumbnail icon
    embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/585763004068839424.png?size=96")
    
    return embed

# Already defined at the top of the file

def create_contact_embed(contact_data):
    """Create a Discord embed for contact form submission"""
    # Create a more visually appealing embed with rich formatting
    embed = discord.Embed(
        title=f"📬 New Contact Form Submission",
        description=f"**{contact_data['subject']}**\n\n{contact_data['message']}",
        color=0x2ecc71,  # Using a vibrant green color
        timestamp=datetime.now()
    )
    
    # Add sender information with icons
    embed.add_field(
        name="👤 From",
        value=f"**{contact_data['name']}**",
        inline=True
    )
    
    embed.add_field(
        name="📧 Email",
        value=f"[{contact_data['email']}](mailto:{contact_data['email']})",
        inline=True
    )
    
    # Add timestamp and additional metadata
    current_time = datetime.now()
    embed.set_footer(
        text=f"Contact Form • {current_time.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    # Add a thumbnail icon
    embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/736613075517603911.png?size=96")
    
    return embed

def send_error_to_discord(error_info):
    """Add error to the queue for processing"""
    global error_channel, discord_bot, error_queue
    
    # Log the error being processed
    logger.info(f"Sending error to Discord: {error_info['error_type']}")
    
    # Check if bot is connected and channel is available
    if not discord_bot:
        logger.warning("Discord bot not initialized")
        return
        
    if not error_channel:
        logger.warning("Discord channel not available")
        return
    
    # Get our shared event loop
    loop = _get_discord_loop()
    
    # Create a future to put the error in the queue
    async def add_to_queue():
        await error_queue.put(error_info)
        logger.info(f"Added to queue: {error_info['error_type']}")
    
    # Schedule the task in the event loop
    try:
        asyncio.run_coroutine_threadsafe(add_to_queue(), loop)
        logger.info(f"Successfully scheduled error for Discord: {error_info['error_type']}")
    except Exception as e:
        logger.error(f"Failed to schedule error for Discord: {str(e)}\n{traceback.format_exc()}")
        
def send_contact_to_discord(contact_info):
    """Add contact form data to the queue for processing"""
    global inbox_channel, discord_bot, contact_queue
    
    # Log the contact form being processed
    logger.info("Sending contact form submission to Discord inbox")
    
    # Check if bot is connected and channel is available
    if not discord_bot:
        logger.warning("Discord bot not initialized")
        return
        
    if not inbox_channel:
        logger.warning("Inbox channel not available")
        return
    
    # Get our shared event loop
    loop = _get_discord_loop()
    
    # Create a future to put the contact form in the queue
    async def add_to_queue():
        await contact_queue.put(contact_info)
        logger.info("Added contact form to queue")
    
    # Schedule the task in the event loop
    try:
        asyncio.run_coroutine_threadsafe(add_to_queue(), loop)
        logger.info("Successfully scheduled contact form for Discord inbox")
    except Exception as e:
        logger.error(f"Failed to schedule contact form for Discord: {str(e)}\n{traceback.format_exc()}")
