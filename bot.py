import os
import sqlite3
import logging
import requests
import msal
import uuid
from datetime import datetime, timedelta
from flask import Flask, request, Response, stream_with_context, redirect
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

# --- Configuration ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID"))
DB_FILE = "music_bot.db"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
TENANT_ID = os.getenv("O365_TENANT_ID")
CLIENT_ID = os.getenv("O365_CLIENT_ID")
CLIENT_SECRET = os.getenv("O365_CLIENT_SECRET")
TARGET_USER_ID = os.getenv("O365_USER_ID")

# --- Initialize ---
app = Flask(__name__)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Application instead of Updater
application = Application.builder().token(BOT_TOKEN).build()

# --- Helper Functions ---
def escape_markdown_v2(text: str) -> str:
    """Escape special characters for MarkdownV2."""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

def get_access_token():
    authority = f"https://login.microsoftonline.com/{TENANT_ID}"
    scope = ["https://graph.microsoft.com/.default"]
    msal_app = msal.ConfidentialClientApplication(
        client_id=CLIENT_ID, authority=authority, client_credential=CLIENT_SECRET
    )
    result = msal_app.acquire_token_for_client(scopes=scope)
    if "access_token" in result:
        return result["access_token"]
    logger.error(f"Failed to acquire token: {result.get('error_description')}")
    return None

def get_download_link(file_id: str):
    token = get_access_token()
    if not token:
        return None, None
    endpoint = f"https://graph.microsoft.com/v1.0/users/{TARGET_USER_ID}/drive/items/{file_id}"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(endpoint, headers=headers)
    if response.status_code == 200:
        data = response.json()
        return data.get("@microsoft.graph.downloadUrl"), data.get("name")
    logger.error(f"Graph API Error getting item: {response.text}")
    return None, None

def get_sharing_link(folder_id: str):
    token = get_access_token()
    if not token:
        return None
    endpoint = f"https://graph.microsoft.com/v1.0/users/{TARGET_USER_ID}/drive/items/{folder_id}/createLink"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"type": "view", "scope": "anonymous"}
    response = requests.post(endpoint, headers=headers, json=payload)
    if response.status_code in (200, 201):
        return response.json().get("link", {}).get("webUrl")
    logger.error(f"Graph API Error creating share link: {response.text}")
    return None

def is_member(user_id: int) -> bool:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT expiry_date, status FROM members WHERE telegram_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        expiry_date_str, status = result
        try:
            expiry_date = datetime.fromisoformat(expiry_date_str)
        except ValueError:
            expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d %H:%M:%S.%f")
        if status == "active" and expiry_date > datetime.now():
            return True
    return False

def update_user_status(user_id: int, status: str) -> bool:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM members WHERE telegram_id = ?", (user_id,))
    result = cursor.fetchone()
    if result:
        cursor.execute("UPDATE members SET status = ? WHERE telegram_id = ?", (status, user_id))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

def search_songs(criteria: str, search_term: str) -> list:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    query = f"SELECT id, artist, album, title FROM songs WHERE {criteria} LIKE ?"
    cursor.execute(query, (f"%{search_term}%",))
    results = cursor.fetchall()
    conn.close()
    return results

# --- Command Handlers ---
async def start(update: Update, context):
    user = update.effective_user
    if is_member(user.id):
        await update.message.reply_text(
            f"👋 Welcome back, {user.first_name}!\n\n"
            "✨ You can search using:\n"
            "`/s_album <album_name>`\n"
            "`/s_artist <artist_name>`",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    else:
        await update.message.reply_text(
            f"🚫 Sorry, {user.first_name}.\n\n"
            "You are not an authorized member. To request access, please use the /join command."
        )

async def join_request(update: Update, context):
    user = update.effective_user
    if is_member(user.id):
        await update.message.reply_text("✨ You are already an active member!")
        return
    user_info = f"👤 **New Join Request**\n\n**Name:** {user.first_name}\n"
    if user.username:
        user_info += f"**Username:** @{user.username}\n"
    user_info += f"**User ID:** `{user.id}`\n\nTo approve:\n`/add_member {user.id} 30`"
    await context.bot.send_message(chat_id=ADMIN_USER_ID, text=user_info, parse_mode=ParseMode.MARKDOWN_V2)
    await update.message.reply_text("✅ Your request has been sent to the admin for approval.")

async def add_member(update: Update, context):
    admin = update.effective_user
    if admin.id != ADMIN_USER_ID:
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /add_member <user_id> <days>")
        return
    user_id = int(context.args[0])
    days = int(context.args[1])
    expiry_date = datetime.now() + timedelta(days=days)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO members (telegram_id, expiry_date, status) VALUES (?, ?, ?)",
        (user_id, expiry_date.isoformat(), "active")
    )
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ User {user_id} added/updated as active member until {expiry_date}")

async def ban_user(update: Update, context):
    admin = update.effective_user
    if admin.id != ADMIN_USER_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /ban <user_id>")
        return
    user_id = int(context.args[0])
    if update_user_status(user_id, "banned"):
        await update.message.reply_text(f"🚫 User {user_id} banned.")
    else:
        await update.message.reply_text("❌ User not found.")

async def unban_user(update: Update, context):
    admin = update.effective_user
    if admin.id != ADMIN_USER_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    user_id = int(context.args[0])
    if update_user_status(user_id, "active"):
        await update.message.reply_text(f"✅ User {user_id} unbanned.")
    else:
        await update.message.reply_text("❌ User not found.")

async def search_album(update: Update, context):
    user = update.effective_user
    if not is_member(user.id):
        return
    if not context.args:
        await update.message.reply_text("✍️ Usage: `/s_album <album_name>`")
        return
    search_term = " ".join(context.args)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, album_name, artist_name FROM albums WHERE album_name LIKE ?", (f"%{search_term}%",))
    results = cursor.fetchall()
    conn.close()
    if not results:
        await update.message.reply_text(f"🤔 No album folders found for: *{search_term}*", parse_mode=ParseMode.MARKDOWN_V2)
    else:
        keyboard = [[InlineKeyboardButton(f"🔗 {album_name}", callback_data=f"albumdl_{album_id}")]
                    for album_id, album_name, artist_name in results[:20]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"💿 *Found {len(results)} album folders for '{search_term}':*",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=reply_markup
        )

async def search_artist(update: Update, context):
    user = update.effective_user
    if not is_member(user.id):
        return
    if not context.args:
        await update.message.reply_text("✍️ Usage: `/s_artist <artist_name>`")
        return
    search_term = " ".join(context.args)
    results = search_songs("artist", search_term)
    if not results:
        await update.message.reply_text(f"🤔 No results for artist: *{search_term}*", parse_mode=ParseMode.MARKDOWN_V2)
    else:
        keyboard = [[InlineKeyboardButton(f"📥 {title}", callback_data=f"dl_{song_id}")]
                    for song_id, artist, album, title in results[:20]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"🎤 *Found {len(results)} songs by artist '{search_term}':*",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=reply_markup
        )

async def button_handler(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if not is_member(user_id):
        await query.edit_message_text(text="🚫 Membership expired.")
        return
    callback_data = query.data
    token = str(uuid.uuid4())
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    if callback_data.startswith("dl_"):
        song_id = int(callback_data.split("_")[1])
        cursor.execute("INSERT INTO download_tokens (token, song_id) VALUES (?, ?)", (token, song_id))
        conn.commit()
        conn.close()
        download_url = f"{WEBHOOK_URL}/download/{token}"
        escaped_url = escape_markdown_v2(download_url)
        logger.info(f"Generated download_url: {download_url}")
        message_text = f"✅ Secure link generated\\!\n\n👉 [Click to download]({escaped_url})\n\n\\_Link expires in 30 minutes and is one-time use\\._"
        logger.info(f"Message text: {message_text}")
        await query.edit_message_text(
            text=message_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            disable_web_page_preview=True
        )
    elif callback_data.startswith("albumdl_"):
        album_id = int(callback_data.split("_")[1])
        cursor.execute("INSERT INTO download_tokens (token, album_id) VALUES (?, ?)", (token, album_id))
        conn.commit()
        conn.close()
        redirect_url = f"{WEBHOOK_URL}/download_album/{token}"
        escaped_url = escape_markdown_v2(redirect_url)
        logger.info(f"Generated redirect_url: {redirect_url}")
        message_text = f"✅ Secure album link generated\\!\n\n👉 [{escape_markdown_v2('Click to download')}]({escaped_url})\n\n\\_Link is one-time use\\._"
        logger.info(f"Message text: {message_text}")
        await query.edit_message_text(
            text=message_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            disable_web_page_preview=True
        )

# --- Flask Routes ---
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
async def webhook_handler():
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.process_update(update)
    return "ok", 200

@app.route("/download/<token>", methods=["GET"])
def download_proxy(token):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT song_id, created_at FROM download_tokens WHERE token = ?", (token,))
    result = cursor.fetchone()
    if not result:
        conn.close()
        return "Invalid or expired link.", 404
    song_id, created_at = result
    created_at = datetime.fromisoformat(created_at)
    if datetime.now() - created_at > timedelta(minutes=30):
        conn.close()
        return "Link expired.", 410
    # delete token immediately (one-time use)
    cursor.execute("DELETE FROM download_tokens WHERE token = ?", (token,))
    conn.commit()
    cursor.execute("SELECT file_id FROM songs WHERE id = ?", (song_id,))
    song_result = cursor.fetchone()
    conn.close()
    if not song_result:
        return "Song not found.", 404
    file_id = song_result[0]
    download_url, file_name = get_download_link(file_id)
    if not download_url:
        return "Could not fetch download link.", 500
    def generate():
        with requests.get(download_url, stream=True) as r:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk
    return Response(stream_with_context(generate()), headers={"Content-Disposition": f"attachment; filename={file_name}"})

@app.route("/download_album/<token>", methods=["GET"])
def download_album_proxy(token):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT album_id FROM download_tokens WHERE token = ?", (token,))
    result = cursor.fetchone()
    if not result:
        conn.close()
        return "Link invalid or used.", 404
    # delete token immediately (one-time use)
    cursor.execute("DELETE FROM download_tokens WHERE token = ?", (token,))
    conn.commit()
    album_id = result[0]
    cursor.execute("SELECT folder_id FROM albums WHERE id = ?", (album_id,))
    album_result = cursor.fetchone()
    conn.close()
    if not album_result:
        return "Album not found.", 404
    real_sharing_link = get_sharing_link(album_result[0])
    if not real_sharing_link:
        return "Could not create a sharing link.", 500
    return redirect(real_sharing_link, code=302)

@app.route("/")
def index():
    return "Bot is running!", 200

# --- Handlers ---
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("join", join_request))
application.add_handler(CommandHandler("add_member", add_member))
application.add_handler(CommandHandler("ban", ban_user))
application.add_handler(CommandHandler("unban", unban_user))
application.add_handler(CommandHandler("s_album", search_album))
application.add_handler(CommandHandler("s_artist", search_artist))
application.add_handler(CallbackQueryHandler(button_handler))

# Set webhook
WEBHOOK_SETUP_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={WEBHOOK_URL}/{BOT_TOKEN}"
logger.info(f"==> SET WEBHOOK (if not set): {WEBHOOK_SETUP_URL}")

# Start the application (handled by Flask in this case)
if __name__ == "__main__":
    import asyncio
    async def set_webhook():
        await application.bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    asyncio.run(set_webhook())
