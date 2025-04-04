import os
import logging
import traceback
from datetime import datetime
import discord
from discord.ext import commands
import asyncio
import threading

# Configure logging - only show warnings and errors
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)

# Global variables
discord_bot = None  # The discord.py bot instance
error_channel = None  # The channel where errors will be sent
error_queue = asyncio.Queue()  # Queue for storing errors to be sent

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
    
    if not discord_token:
        logger.warning("DISCORD_TOKEN not found in environment variables. Discord bot will not be started.")
        return None
    
    # Set intents for the bot - only use non-privileged intents
    intents = discord.Intents.default()
    intents.message_content = False  # This requires privileged intents, so we disable it
    
    # Create bot instance - we don't need command prefix for a notification bot
    discord_bot = commands.Bot(command_prefix="!", intents=intents)
    
    @discord_bot.event
    async def on_ready():
        """Event triggered when the bot is ready"""
        global error_channel
        logger.info(f"Logged in as {discord_bot.user.name} ({discord_bot.user.id})")
        
        # Get the error reporting channel
        if channel_id:
            try:
                # Try to get the channel by ID
                error_channel = discord_bot.get_channel(int(channel_id))
                
                # If not found, try fetching it
                if not error_channel:
                    error_channel = await discord_bot.fetch_channel(int(channel_id))
                    
                logger.info(f"Error channel set to: {error_channel.name} (ID: {error_channel.id})")
                
                # Test send a message to verify permissions
                test_embed = discord.Embed(
                    title="📢 Error Monitoring Bot Connected",
                    description="The Flask application error monitor is now online and ready to report errors.",
                    color=discord.Color.green()
                )
                test_embed.set_footer(text=f"Initialized at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
                await error_channel.send(embed=test_embed)
                logger.info("Successfully sent test message to Discord channel")
                
            except Exception as e:
                logger.error(f"Failed to get Discord channel: {str(e)}\n{traceback.format_exc()}")
        else:
            logger.warning("DISCORD_CHANNEL_ID not set. Errors will not be reported.")
        
        # Start the error processing task in the current event loop
        asyncio.create_task(process_error_queue())
    
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
    embed = discord.Embed(
        title=f"❌ Error: {error_data['error_type']}",
        description=error_data['message'],
        color=discord.Color.red(),
        timestamp=datetime.now()
    )
    
    embed.add_field(name="Route", value=error_data['route'], inline=False)
    embed.add_field(name="Method", value=error_data['method'], inline=True)
    embed.add_field(name="Status Code", value=error_data['status_code'], inline=True)
    
    if 'user_agent' in error_data:
        embed.add_field(name="User Agent", value=error_data['user_agent'], inline=False)
    
    if error_data.get('traceback'):
        # Truncate traceback to fit in Discord embed (max 1024 chars per field)
        traceback_str = error_data['traceback']
        if len(traceback_str) > 1000:
            traceback_str = traceback_str[:997] + "..."
        embed.add_field(name="Traceback", value=f"```python\n{traceback_str}\n```", inline=False)
    
    embed.set_footer(text=f"Flask Application Error Monitor")
    
    return embed

# Already defined at the top of the file

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
