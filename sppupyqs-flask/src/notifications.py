# Discord webhook calls are synchronous — threading was removed because
# Vercel's serverless runtime kills background threads after the response.
# The timeout is short (3s) to avoid blocking the user experience.
import requests
from datetime import datetime, timezone
from .config import DISCORD_WEBHOOK_URL

_http = requests.Session()


def _safe_text(value, fallback, limit):
    text = (value or fallback or "").strip()
    if not text:
        text = fallback
    if len(text) > limit:
        return text[:limit - 3] + "..."
    return text


def _safe_field(name, value, inline=True, limit=1024):
    return {
        "name": name,
        "value": _safe_text(value, "Not provided", limit),
        "inline": inline
    }


def send_discord_notification(notification_type, data):
    if not DISCORD_WEBHOOK_URL:
        return

    embed = _build_discord_embed(notification_type, data)
    if not embed:
        return

    payload = {
        "username": "SPPU PYQs",
        "embeds": [embed]
    }
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "SPPU-PYQs-Bot/1.0 (Vercel; +https://sppupyqs.vercel.app)"
    }

    try:
        response = _http.post(
            DISCORD_WEBHOOK_URL,
            json=payload,
            headers=headers,
            timeout=3,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException:
        pass


def send_discord_notification_async(notification_type, data):
    send_discord_notification(notification_type, data)
    return True


def _build_discord_embed(notification_type, data):
    timestamp = datetime.now(timezone.utc).isoformat()

    if notification_type == "contact":
        return {
            "title": "New Contact Query",
            "color": 15158332,
            "timestamp": timestamp,
            "description": "A new contact form message was received.",
            "fields": [
                _safe_field("From", data.get("name"), True),
                _safe_field("Email", data.get("email"), True),
                _safe_field("Message", data.get("message"), False, 500),
                _safe_field("IP", data.get("ip_address"), True),
                _safe_field("Source", data.get("source_url"), False),
                _safe_field("User-Agent", data.get("user_agent"), False)
            ]
        }

    return None
