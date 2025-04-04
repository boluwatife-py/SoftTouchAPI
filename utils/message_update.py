import discord, os
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True  # Enable message content intent
bot = commands.Bot(command_prefix='!', intents=intents)

# Bot token (replace with your actual token from Discord Developer Portal)
TOKEN = os.getenv("DISCORD_TOKEN")

# Event: Bot is ready
@bot.event
async def on_ready():
    print(f'Bot has connected to Discord as {bot.user}')

# Function to send a message to a specific channel
async def send_message(message, channel_id=None):
    if channel_id:
        channel = bot.get_channel(channel_id)
        if channel:
            await channel.send(message)
        else:
            print(f"Channel with ID {channel_id} not found.")
    else:
        # Send to the first available channel the bot can see (for simplicity)
        for guild in bot.guilds:
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    await channel.send(message)
                    return
            print("No accessible channel found to send the message.")

# Error handler
@bot.event
async def on_command_error(ctx, error):
    await ctx.send(f"An error occurred: {error}")
