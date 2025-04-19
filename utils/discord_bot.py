import os
import logging
from datetime import datetime
import requests


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


error_channel_id = None
inbox_channel_id = None
_bot_initialized = False

def setup_discord_bot():
    """Initialize and setup the Discord bot only once"""
    global error_channel_id, inbox_channel_id, _bot_initialized
    if _bot_initialized:
        logger.info("Discord bot already initialized, skipping setup")
        return

    discord_token = os.environ.get("DISCORD_TOKEN")
    error_channel_id = os.environ.get("DISCORD_CHANNEL_ID")
    inbox_channel_id = os.environ.get("DISCORD_INBOX_CHANNEL_ID")

    if not discord_token:
        logger.warning("DISCORD_TOKEN not found, Discord bot disabled")
        return

    _bot_initialized = True
    logger.info("Discord bot initialized")

def send_error_embed(channel_id, error_data, token):
    """Send an error embed to a Discord channel"""
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
            },
            {
                "name": "🌐 User Agent",
                "value": f"`{error_data['user_agent']}`",  # Always include, with fallback
                "inline": False
            }
        ]
    }
    if error_data.get('traceback'):
        traceback_str = error_data['traceback'][:997] + "..." if len(error_data['traceback']) > 1000 else error_data['traceback']
        embed["fields"].append({
            "name": "📋 Traceback",
            "value": f"```python\n{traceback_str}\n```",
            "inline": False
        })

    send_embed_to_channel(channel_id, embed, token)

def send_contact_embed(channel_id, contact_data, token):
    """Send a contact embed to a Discord channel"""
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
    send_embed_to_channel(channel_id, embed, token)

def send_embed_to_channel(channel_id, embed, token):
    """Send an embed to a Discord channel using HTTP"""
    payload = {"embeds": [embed]}
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send message to channel {channel_id}: {e}")

def send_error_to_discord(error_info):
    """Send an error message to Discord"""
    discord_token = os.environ.get("DISCORD_TOKEN")
    if not _bot_initialized or not error_channel_id or not discord_token:
        logger.warning("Discord bot or channel not ready for error reporting")
        return
    send_error_embed(error_channel_id, error_info, discord_token)

def send_contact_to_discord(contact_info):
    """Send a contact message to Discord"""
    discord_token = os.environ.get("DISCORD_TOKEN")
    if not _bot_initialized or not inbox_channel_id or not discord_token:
        logger.warning("Discord bot or channel not ready for contact reporting")
        return
    send_contact_embed(inbox_channel_id, contact_info, discord_token)