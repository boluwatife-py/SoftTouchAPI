from datetime import datetime
from discord.ext import commands
import asyncio, threading, discord, logging, os

# Configure logging
logger = logging.getLogger(__name__)

# Global variables
discord_bot = None
client = None
error_channel = None
error_queue = asyncio.Queue()

def setup_discord_bot():
    """Initialize and setup the Discord bot"""
    global discord_bot, client
    
    # Get Discord token from environment
    discord_token = os.environ.get("DISCORD_TOKEN")
    channel_id = os.environ.get("DISCORD_CHANNEL_ID")
    
    if not discord_token:
        logger.warning("DISCORD_TOKEN not found in environment variables. Discord bot will not be started.")
        return None
    
    # Set intents for the bot
    intents = discord.Intents.default()
    intents.message_content = True
    
    # Create bot instance
    discord_bot = commands.Bot(command_prefix="!", intents=intents)
    
    @discord_bot.event
    async def on_ready():
        """Event triggered when the bot is ready"""
        global error_channel
        logger.info(f"Logged in as {discord_bot.user.name} ({discord_bot.user.id})")
        
        # Get the error reporting channel
        if channel_id:
            try:
                error_channel = discord_bot.get_channel(int(channel_id))
                if not error_channel:
                    error_channel = await discord_bot.fetch_channel(int(channel_id))
                logger.info(f"Error channel set to: {error_channel.name}")
            except Exception as e:
                logger.error(f"Failed to get Discord channel: {str(e)}")
        else:
            logger.warning("DISCORD_CHANNEL_ID not set. Errors will not be reported.")
        
        # Start the error processing task
        asyncio.create_task(process_error_queue())
    
    async def process_error_queue():
        """Process errors from the queue and send them to Discord"""
        while True:
            try:
                error_data = await error_queue.get()
                if error_channel:
                    embed = create_error_embed(error_data)
                    await error_channel.send(embed=embed)
                error_queue.task_done()
            except Exception as e:
                logger.error(f"Error processing Discord error queue: {str(e)}")
            await asyncio.sleep(1)  # Prevent API rate limiting
    
    # Start the bot in a separate thread
    def run_discord_bot():
        """Run the Discord bot in a separate thread"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(discord_bot.start(discord_token))
        except Exception as e:
            logger.error(f"Discord bot error: {str(e)}")
    
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

def send_error_to_discord(error_info):
    """Add error to the queue for processing"""
    if error_queue:
        asyncio.run_coroutine_threadsafe(error_queue.put(error_info), asyncio.get_event_loop())
        logger.debug(f"Added error to Discord queue: {error_info['error_type']}")
    else:
        logger.warning("Error queue not initialized, can't send error to Discord")
