import os
import sqlite3
import logging
import requests
import msal
import uuid
import time
from datetime import datetime, timedelta
from flask import Flask, request, Response, stream_with_context, redirect
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
    if not token: return None, None
    endpoint = f"https://graph.microsoft.com/v1.0/users/{TARGET_USER_ID}/drive/items/{file_id}"
    headers = {'Authorization': f'Bearer {token}'}
    response = requests.get(endpoint, headers=headers)
    if response.status_code == 200:
        data = response.json()
        return data.get('@microsoft.graph.downloadUrl'), data.get('name')
    else:
        logger.error(f"Graph API Error getting item: {response.text}")
        return None, None

def get_sharing_link(folder_id: str):
    token = get_access_token()
    if not token: return None
    endpoint = f"https://graph.microsoft.com/v1.0/users/{TARGET_USER_ID}/drive/items/{folder_id}/createLink"
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    payload = {"type": "view", "scope": "anonymous"}
    response = requests.post(endpoint, headers=headers, json=payload)
    if response.status_code == 200 or response.status_code == 201:
        return response.json().get('link', {}).get('webUrl')
    else:
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
        update.message.reply_text(f"🚫 Sorry, {user.first_name}.\n\nYou are not an authorized member. To request access, please use the /join command.")

def join_request(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    if is_member(user.id):
        update.message.reply_text("✨ You are already an active member!")
        return
    user_info = f"👤 **New Join Request**\n\n**Name:** {user.first_name}\n"
    if user.username: user_info += f"**Username:** @{user.username}\n"
    user_info += f"**User ID:** `{user.id}`\n\nTo approve:\n`/add_member {user.id} 30`"
    try:
        context.bot.send_message(chat_id=ADMIN_USER_ID, text=user_info, parse_mode=ParseMode.MARKDOWN)
        update.message.reply_text("✅ Your request has been sent to the admin for approval.")
    except Exception as e:
        logger.error(f"Failed to send join request notification for user {user.id}: {e}")
        update.message.reply_text("😔 Sorry, an error occurred. Please contact the admin directly.")

def add_member(update: Update, context: CallbackContext) -> None:
    admin = update.effective_user
    if admin.id != ADMIN_USER_ID: return
    # ... (rest of the function is same as previous complete version)
    
def ban_user(update: Update, context: CallbackContext) -> None:
    admin = update.effective_user
    if admin.id != ADMIN_USER_ID: return
    # ... (rest of the function is same as previous complete version)

def unban_user(update: Update, context: CallbackContext) -> None:
    admin = update.effective_user
    if admin.id != ADMIN_USER_ID: return
    # ... (rest of the function is same as previous complete version)

def search_album(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    if not is_member(user.id): return
    if not context.args:
        update.message.reply_text("✍️ Usage: `/s_album <album_name>`")
        return
    search_term = " ".join(context.args)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, album_name, artist_name FROM albums WHERE album_name LIKE ?", (f'%{search_term}%',))
    results = cursor.fetchall()
    conn.close()
    if not results:
        update.message.reply_text(f"🤔 No album folders found for: *{search_term}*", parse_mode=ParseMode.MARKDOWN)
    else:
        keyboard = [[InlineKeyboardButton(f"🔗 {album_name}", callback_data=f"albumdl_{album_id}")] for album_id, album_name, artist_name in results[:20]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text(f"💿 *Found {len(results)} album folders for '{search_term}':*", parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

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
    token = str(uuid.uuid4())
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    if callback_data.startswith("dl_"):
        song_id = int(callback_data.split("_")[1])
        cursor.execute("INSERT INTO download_tokens (token, song_id) VALUES (?, ?)", (token, song_id))
        conn.commit()
        conn.close()
        download_url = f"{WEBHOOK_URL}/download/{token}"
        query.edit_message_text(text=f"✅ Secure link generated!\n\n👉 [Click to download]({download_url})\n\n_Link expires in 30 minutes._", parse_mode=ParseMode.MARKDOWN)
    elif callback_data.startswith("albumdl_"):
        album_id = int(callback_data.split("_")[1])
        cursor.execute("INSERT INTO download_tokens (token, album_id) VALUES (?, ?)", (token, album_id))
        conn.commit()
        conn.close()
        redirect_url = f"{WEBHOOK_URL}/download_album/{token}"
        query.edit_message_text(text=f"✅ Secure album link generated!\n\n👉 [Click to open folder]({redirect_url})\n\n_Link is one-time use._", parse_mode=ParseMode.MARKDOWN)

# --- Flask Web Routes ---
@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook_handler():
    update = Update.de_json(request.get_json(force=True), updater.bot)
    dispatcher.process_update(update)
    return 'ok', 200

@app.route('/download/<token>', methods=['GET'])
def download_proxy(token):
    # ... (Full logic from previous complete version) ...

@app.route('/download_album/<token>', methods=['GET'])
def download_album_proxy(token):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT album_id FROM download_tokens WHERE token = ?", (token,))
    result = cursor.fetchone()
    if not result:
        conn.close()
        return "Link invalid or used.", 404
    cursor.execute("DELETE FROM download_tokens WHERE token = ?", (token,))
    conn.commit()
    album_id = result[0]
    cursor.execute("SELECT folder_id FROM albums WHERE id = ?", (album_id,))
    album_result = cursor.fetchone()
    conn.close()
    if not album_result: return "Album not found.", 404
    real_sharing_link = get_sharing_link(album_result[0])
    if not real_sharing_link:
        return "Could not create a sharing link.", 500
    return redirect(real_sharing_link, code=302)

@app.route('/')
def index():
    return 'Bot is running!', 200

# --- Register all handlers ---
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("join", join_request))
dispatcher.add_handler(CommandHandler("add_member", add_member))
dispatcher.add_handler(CommandHandler("ban", ban_user))
dispatcher.add_handler(CommandHandler("unban", unban_user))
dispatcher.add_handler(CommandHandler("s_album", search_album))
dispatcher.add_handler(CommandHandler("s_artist", search_artist))
dispatcher.add_handler(CallbackQueryHandler(button_handler))

# Set the webhook URL (This is for logging purposes)
WEBHOOK_SETUP_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={WEBHOOK_URL}/{BOT_TOKEN}"
logger.info(f"==> SET WEBHOOK (if not set): {WEBHOOK_SETUP_URL}")
