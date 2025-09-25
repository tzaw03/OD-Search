import os
import sqlite3
import logging
from datetime import datetime, timedelta
from telegram import Update, ParseMode
from telegram.ext import Updater, CommandHandler, CallbackContext

# --- Configuration ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID"))
DB_FILE = "music_bot.db"
WEBHOOK_URL = os.getenv("WEBHOOK_URL") 

# Enable logging
# ... (No changes here) ...
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Helper Functions ---
def is_member(user_id: int) -> bool:
    # ... (No changes here) ...
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
    # ... (No changes here) ...
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

# --- Command Handlers ---
def start(update: Update, context: CallbackContext) -> None:
    # ... (No changes here) ...
    user = update.effective_user
    user_id = user.id
    logger.info(f"🚀 User {user.first_name} ({user_id}) started the bot.")
    if is_member(user_id):
        update.message.reply_text(f"👋 Welcome back, {user.first_name}!\n\n✨ You can search using:\n`/s_album <album_name>`\n`/s_artist <artist_name>`")
    else:
        update.message.reply_text(f"🚫 Sorry, {user.first_name}.\n\nYou are not an authorized member of this bot.")

# --- Admin Commands ---
def add_member(update: Update, context: CallbackContext) -> None:
    # ... (No changes here) ...
    # ... (Same as previous version)

def ban_user(update: Update, context: CallbackContext) -> None:
    # ... (No changes here) ...
    # ... (Same as previous version)

def unban_user(update: Update, context: CallbackContext) -> None:
    # ... (No changes here) ...
    # ... (Same as previous version)

# --- NEW: Member Search Commands ---
def search_songs(criteria: str, search_term: str) -> list:
    """Database ထဲတွင် သီချင်းရှာသော helper function"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Use LIKE for partial, case-insensitive matching
    query = f"SELECT artist, album, title FROM songs WHERE {criteria} LIKE ?"
    cursor.execute(query, (f'%{search_term}%',))
    results = cursor.fetchall()
    conn.close()
    return results

def search_album(update: Update, context: CallbackContext) -> None:
    """Album နာမည်ဖြင့် သီချင်းရှာရန်"""
    user = update.effective_user
    if not is_member(user.id):
        update.message.reply_text("🚫 Sorry, this feature is for members only.")
        return

    if not context.args:
        update.message.reply_text("✍️ Please provide an album name to search.\nUsage: `/s_album <album_name>`")
        return
    
    search_term = " ".join(context.args)
    logger.info(f"Member {user.id} is searching for album: {search_term}")
    
    results = search_songs("album", search_term)
    
    if not results:
        update.message.reply_text(f"🤔 No results found for album: *{search_term}*", parse_mode=ParseMode.MARKDOWN)
    else:
        message = f"🎵 *Found {len(results)} songs for album '{search_term}':*\n\n"
        for i, (artist, album, title) in enumerate(results, 1):
            message += f"*{i}.* `{title}` by {artist}\n"
        update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

def search_artist(update: Update, context: CallbackContext) -> None:
    """Artist နာမည်ဖြင့် သီချင်းရှာရန်"""
    user = update.effective_user
    if not is_member(user.id):
        update.message.reply_text("🚫 Sorry, this feature is for members only.")
        return

    if not context.args:
        update.message.reply_text("✍️ Please provide an artist name to search.\nUsage: `/s_artist <artist_name>`")
        return
    
    search_term = " ".join(context.args)
    logger.info(f"Member {user.id} is searching for artist: {search_term}")

    results = search_songs("artist", search_term)

    if not results:
        update.message.reply_text(f"🤔 No results found for artist: *{search_term}*", parse_mode=ParseMode.MARKDOWN)
    else:
        message = f"🎤 *Found {len(results)} songs by artist '{search_term}':*\n\n"
        for i, (artist, album, title) in enumerate(results, 1):
            message += f"*{i}.* `{title}` from album '{album}'\n"
        update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

# --- Main Function ---
def main() -> None:
    # ... (No changes here) ...
    if not BOT_TOKEN or not WEBHOOK_URL or not ADMIN_USER_ID:
        logger.error("❌ BOT_TOKEN, WEBHOOK_URL, and ADMIN_USER_ID secrets must be set!")
        return
    updater = Updater(BOT_TOKEN)
    dispatcher = updater.dispatcher
    
    # Admin and general command handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("add_member", add_member))
    dispatcher.add_handler(CommandHandler("ban", ban_user))
    dispatcher.add_handler(CommandHandler("unban", unban_user))
    
    # --- NEW: Register Search Commands ---
    dispatcher.add_handler(CommandHandler("s_album", search_album))
    dispatcher.add_handler(CommandHandler("s_artist", search_artist))

    PORT = int(os.environ.get('PORT', '8443'))
    updater.start_webhook(listen="0.0.0.0",
                          port=PORT,
                          url_path=BOT_TOKEN,
                          webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    logger.info(f"✅ Bot has started on webhook mode, listening on port {PORT}.")
    updater.idle()

if __name__ == '__main__':
    main()
