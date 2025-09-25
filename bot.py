import os
import sqlite3
import logging
import requests
import msal
import uuid
import time
from datetime import datetime, timedelta
from flask import Flask, request, Response, stream_with_context
from telegram import Update, ParseMode, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackContext, CallbackQueryHandler, Dispatcher

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
updater = Updater(BOT_TOKEN)
dispatcher = updater.dispatcher
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
download_tokens = {}

# --- Helper Functions ---
def get_access_token():
    authority = f"https://login.microsoftonline.com/{TENANT_ID}"
    scope = ["https://graph.microsoft.com/.default"]
    msal_app = msal.ConfidentialClientApplication(client_id=CLIENT_ID, authority=authority, client_credential=CLIENT_SECRET)
    result = msal_app.acquire_token_for_client(scopes=scope)
    if "access_token" in result:
        return result['access_token']
    else:
        logger.error(f"Failed to acquire token: {result.get('error_description')}")
        return None

def get_download_link(file_id: str):
    token = get_access_token()
    if not token:
        return None, None
    endpoint = f"https://graph.microsoft.com/v1.0/users/{TARGET_USER_ID}/drive/items/{file_id}"
    headers = {'Authorization': f'Bearer {token}'}
    response = requests.get(endpoint, headers=headers)
    if response.status_code == 200:
        data = response.json()
        return data.get('@microsoft.graph.downloadUrl'), data.get('name')
    else:
        logger.error(f"Graph API Error getting item: {response.text}")
        return None, None

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
            expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d %H:%M:%S.%f')
        if status == 'active' and expiry_date > datetime.now():
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
    cursor.execute(query, (f'%{search_term}%',))
    results = cursor.fetchall()
    conn.close()
    return results

# --- Command & Callback Handlers ---
def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    logger.info(f"🚀 User {user.first_name} ({user.id}) started the bot.")
    if is_member(user.id):
        update.message.reply_text(f"👋 Welcome back, {user.first_name}!\n\n✨ You can search using:\n`/s_album <album_name>`\n`/s_artist <artist_name>`")
    else:
        update.message.reply_text(f"🚫 Sorry, {user.first_name}.\n\nYou are not an authorized member of this bot.")

def add_member(update: Update, context: CallbackContext) -> None:
    admin = update.effective_user
    if admin.id != ADMIN_USER_ID: return
    if not context.args or len(context.args) > 2:
        update.message.reply_text("✍️ Usage: `/add_member <user_id> [days]`")
        return
    try:
        target_user_id = int(context.args[0])
        days_to_add = int(context.args[1]) if len(context.args) == 2 else 30
    except ValueError:
        update.message.reply_text("❌ Error: User ID and Days must be numbers.")
        return
    expiry_date = datetime.now() + timedelta(days=days_to_add)
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO members (telegram_id, expiry_date, status, first_name) VALUES (?, ?, 'active', 'N/A') ON CONFLICT(telegram_id) DO UPDATE SET expiry_date = excluded.expiry_date, status = 'active';", (target_user_id, expiry_date))
        conn.commit()
        conn.close()
        expiry_date_str = expiry_date.strftime('%Y-%m-%d')
        update.message.reply_text(f"✅ Success!\nUser `{target_user_id}` is now an active member.\nValid until: *{expiry_date_str}*.", parse_mode=ParseMode.MARKDOWN)
        logger.info(f"Admin ({admin.id}) added/updated user {target_user_id}.")
    except Exception as e:
        logger.error(f"DB error in add_member: {e}")
        update.message.reply_text("❌ DB error occurred.")

def ban_user(update: Update, context: CallbackContext) -> None:
    admin = update.effective_user
    if admin.id != ADMIN_USER_ID: return
    if not context.args or len(context.args) != 1:
        update.message.reply_text("✍️ Usage: `/ban <user_id>`")
        return
    try:
        target_user_id = int(context.args[0])
        if update_user_status(target_user_id, 'banned'):
            update.message.reply_text(f"🚫 User `{target_user_id}` has been banned.", parse_mode=ParseMode.MARKDOWN)
        else:
            update.message.reply_text(f"🤔 User `{target_user_id}` not found.", parse_mode=ParseMode.MARKDOWN)
    except ValueError:
        update.message.reply_text("❌ Error: User ID must be a number.")

def unban_user(update: Update, context: CallbackContext) -> None:
    admin = update.effective_user
    if admin.id != ADMIN_USER_ID: return
    if not context.args or len(context.args) != 1:
        update.message.reply_text("✍️ Usage: `/unban <user_id>`")
        return
    try:
        target_user_id = int(context.args[0])
        if update_user_status(target_user_id, 'active'):
            update.message.reply_text(f"✅ User `{target_user_id}` has been unbanned.", parse_mode=ParseMode.MARKDOWN)
        else:
            update.message.reply_text(f"🤔 User `{target_user_id}` not found.", parse_mode=ParseMode.MARKDOWN)
    except ValueError:
        update.message.reply_text("❌ Error: User ID must be a number.")

def search_album(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    if not is_member(user.id): return
    if not context.args:
        update.message.reply_text("✍️ Usage: `/s_album <album_name>`")
        return
    search_term = " ".join(context.args)
    results = search_songs("album", search_term)
    if not results:
        update.message.reply_text(f"🤔 No results for album: *{search_term}*", parse_mode=ParseMode.MARKDOWN)
    else:
        keyboard = [[InlineKeyboardButton(f"📥 {title}", callback_data=f"dl_{song_id}")] for song_id, artist, album, title in results[:20]] # Limit results to 20 to avoid message overload
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text(f"🎵 *Found {len(results)} songs for album '{search_term}':*", parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

def search_artist(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    if not is_member(user.id): return
    if not context.args:
        update.message.reply_text("✍️ Usage: `/s_artist <artist_name>`")
        return
    search_term = " ".join(context.args)
    results = search_songs("artist", search_term)
    if not results:
        update.message.reply_text(f"🤔 No results for artist: *{search_term}*", parse_mode=ParseMode.MARKDOWN)
    else:
        keyboard = [[InlineKeyboardButton(f"📥 {title}", callback_data=f"dl_{song_id}")] for song_id, artist, album, title in results[:20]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text(f"🎤 *Found {len(results)} songs by artist '{search_term}':*", parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

def button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    if not is_member(user_id):
        query.edit_message_text(text="🚫 Membership expired.")
        return
    callback_data = query.data
    if callback_data.startswith("dl_"):
        song_id = int(callback_data.split("_")[1])
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT file_id FROM songs WHERE id = ?", (song_id,))
        result = cursor.fetchone()
        conn.close()
        if result:
            token = str(uuid.uuid4())
            download_tokens[token] = {'file_id': result[0], 'timestamp': time.time()}
            download_url = f"{WEBHOOK_URL}/download/{token}"
            query.edit_message_text(text=f"✅ Secure link generated!\n\n👉 [Click here to download]({download_url})\n\n_Link is valid for 60 seconds._", parse_mode=ParseMode.MARKDOWN)
        else:
            query.edit_message_text(text="🤔 Song not found.")

# --- Flask Web Routes ---
@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook_handler():
    update = Update.de_json(request.get_json(force=True), updater.bot)
    dispatcher.process_update(update)
    return 'ok', 200

@app.route('/download/<token>', methods=['GET'])
def download_proxy(token):
    token_data = download_tokens.get(token)
    if not token_data or time.time() - token_data['timestamp'] > 60:
        download_tokens.pop(token, None)
        return "Link expired or invalid.", 410
    download_tokens.pop(token, None)
    file_id = token_data['file_id']
    real_download_url, file_name = get_download_link(file_id)
    if not real_download_url:
        return "Failed to fetch from cloud storage.", 500
    req = requests.get(real_download_url, stream=True)
    return Response(stream_with_context(req.iter_content(chunk_size=1024*1024)), headers={'Content-Disposition': f'attachment; filename="{file_name}"'})

@app.route('/')
def index():
    return 'Bot is running!', 200

# --- Register all handlers ---
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("add_member", add_member))
dispatcher.add_handler(CommandHandler("ban", ban_user))
dispatcher.add_handler(CommandHandler("unban", unban_user))
dispatcher.add_handler(CommandHandler("s_album", search_album))
dispatcher.add_handler(CommandHandler("s_artist", search_artist))
dispatcher.add_handler(CallbackQueryHandler(button_handler))

# Set the webhook URL (This should be done once)
WEBHOOK_SETUP_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={WEBHOOK_URL}/{BOT_TOKEN}"
logger.info(f"==> SET WEBHOOK (if not set): {WEBHOOK_SETUP_URL}")
