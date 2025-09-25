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

# In-memory store for one-time download tokens
# Format: { 'token': {'song_id': 123, 'timestamp': 167...} }
download_tokens = {}

# --- Helper Functions ---
def get_access_token():
    # ... (Same as before) ...
    
def get_download_link(file_id: str):
    # ... (Same as before) ...

def is_member(user_id: int) -> bool:
    # ... (Same as before) ...

# --- Admin Commands ---
def add_member(update: Update, context: CallbackContext) -> None:
    # ... (Same as before) ...
    
def ban_user(update: Update, context: CallbackContext) -> None:
    # ... (Same as before) ...
    
def unban_user(update: Update, context: CallbackContext) -> None:
    # ... (Same as before) ...
    
# --- Search and Callback Handlers ---
def search_album(update: Update, context: CallbackContext) -> None:
    # ... (Same as before) ...

def search_artist(update: Update, context: CallbackContext) -> None:
    # ... (Same as before) ...

def button_handler(update: Update, context: CallbackContext) -> None:
    """Download button နှိပ်လိုက်တိုင်း အလုပ်လုပ်မယ့် function"""
    query = update.callback_query
    query.answer()
    
    user_id = query.from_user.id
    if not is_member(user_id):
        query.edit_message_text(text="🚫 Sorry, you are no longer an active member.")
        return

    callback_data = query.data
    if callback_data.startswith("dl_"):
        song_id = int(callback_data.split("_")[1])
        
        # Generate a unique, one-time token
        token = str(uuid.uuid4())
        download_tokens[token] = {'song_id': song_id, 'timestamp': time.time()}
        
        # Send the proxied download link to the user
        download_url = f"{WEBHOOK_URL}/download/{token}"
        
        query.edit_message_text(
            text=f"✅ Your secure download link is ready!\n\n👉 [Click here to download]({download_url})\n\n_Note: This link is for one-time use only and will expire in 60 seconds._",
            parse_mode=ParseMode.MARKDOWN
        )

# --- Flask Web Routes ---
@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook_handler():
    """Handles updates from Telegram."""
    update = Update.de_json(request.get_json(force=True), updater.bot)
    dispatcher.process_update(update)
    return 'ok', 200

@app.route('/download/<token>', methods=['GET'])
def download_proxy(token):
    """Handles the secure, one-time download link."""
    # 1. Validate Token
    token_data = download_tokens.get(token)
    if not token_data:
        return "Download link is invalid or has already been used.", 404

    # 2. Check Expiry (60 seconds)
    if time.time() - token_data['timestamp'] > 60:
        download_tokens.pop(token, None)
        return "Download link has expired.", 410
        
    # 3. Invalidate token immediately (one-time use)
    download_tokens.pop(token, None)
    
    # 4. Get File Info from DB
    song_id = token_data['song_id']
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT file_id, file_name FROM songs WHERE id = ?", (song_id,))
    result = cursor.fetchone()
    conn.close()

    if not result:
        return "Song not found in database.", 404
        
    file_id, file_name = result
    
    # 5. Get Real Download Link from MS Graph
    real_download_url = get_download_link(file_id)
    if not real_download_url:
        return "Could not fetch download link from cloud storage.", 500
        
    # 6. Stream the file to the user
    req = requests.get(real_download_url, stream=True)
    return Response(stream_with_context(req.iter_content(chunk_size=1024)), headers={
        'Content-Disposition': f'attachment; filename="{file_name}"'
    })

@app.route('/')
def index():
    return 'Bot is running!', 200

# --- Register all handlers ---
def register_handlers(dp: Dispatcher):
    # ... (Register all handlers: start, add_member, ban, unban, s_album, s_artist) ...
    dp.add_handler(CallbackQueryHandler(button_handler))

# --- Main Setup ---
# ... (All your functions should be defined before this point) ...
# ... Make sure to copy all the functions from our previous versions into this file ...
register_handlers(dispatcher)
WEBHOOK_SETUP_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={WEBHOOK_URL}/{BOT_TOKEN}"
logger.info(f"SET YOUR WEBHOOK MANUALLY (if needed): {WEBHOOK_SETUP_URL}")
