import os
import sqlite3
import logging
import requests
import msal
from datetime import datetime, timedelta
from telegram import Update, ParseMode, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackContext, CallbackQueryHandler

# --- Configuration ---
# GitHub Secrets/Environment Variables
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID"))
DB_FILE = "music_bot.db"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# OneDrive App Credentials
TENANT_ID = os.getenv("O365_TENANT_ID")
CLIENT_ID = os.getenv("O365_CLIENT_ID")
CLIENT_SECRET = os.getenv("O365_CLIENT_SECRET")
TARGET_USER_ID = os.getenv("O365_USER_ID")

# Enable logging
# ... (No changes here) ...
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Microsoft Graph API Helper ---
def get_access_token():
    """Microsoft Graph API အတွက် Access Token ရယူခြင်း"""
    authority = f"https://login.microsoftonline.com/{TENANT_ID}"
    scope = ["https://graph.microsoft.com/.default"]
    app = msal.ConfidentialClientApplication(client_id=CLIENT_ID, authority=authority, client_credential=CLIENT_SECRET)
    result = app.acquire_token_for_client(scopes=scope)
    if "access_token" in result:
        return result['access_token']
    else:
        logger.error(f"Failed to acquire token: {result.get('error_description')}")
        return None

def get_download_link(file_id: str):
    """OneDrive File ID ကိုသုံးပြီး download link ရယူခြင်း"""
    token = get_access_token()
    if not token:
        return None
    
    endpoint = f"https://graph.microsoft.com/v1.0/users/{TARGET_USER_ID}/drive/items/{file_id}"
    headers = {'Authorization': f'Bearer {token}'}
    response = requests.get(endpoint, headers=headers)
    
    if response.status_code == 200:
        # Temporary download URL is in this key
        return response.json().get('@microsoft.graph.downloadUrl')
    else:
        logger.error(f"Graph API Error getting item: {response.text}")
        return None

# --- Membership & Command Handlers (with updates) ---
def is_member(user_id: int) -> bool:
    # ... (No changes here) ...
    # ... (Same as previous version)
    
def start(update: Update, context: CallbackContext) -> None:
    # ... (No changes here) ...
    # ... (Same as previous version)
    
# --- Admin Commands (No Changes) ---
def add_member(update: Update, context: CallbackContext) -> None:
    # ... (No changes here) ...
    # ... (Same as previous version)

def ban_user(update: Update, context: CallbackContext) -> None:
    # ... (No changes here) ...
    # ... (Same as previous version)

def unban_user(update: Update, context: CallbackContext) -> None:
    # ... (No changes here) ...
    # ... (Same as previous version)

# --- Member Search Commands (UPDATED) ---
def search_songs(criteria: str, search_term: str) -> list:
    """Database ထဲတွင် သီချင်းရှာသော helper function"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Now we also need the file_id
    query = f"SELECT id, file_id, artist, album, title FROM songs WHERE {criteria} LIKE ?"
    cursor.execute(query, (f'%{search_term}%',))
    results = cursor.fetchall()
    conn.close()
    return results

def search_album(update: Update, context: CallbackContext) -> None:
    # ... (Logic to check member and parse arguments is the same) ...
    user = update.effective_user
    if not is_member(user.id): # ...
        return
    if not context.args: # ...
        return
        
    search_term = " ".join(context.args)
    logger.info(f"Member {user.id} is searching for album: {search_term}")
    results = search_songs("album", search_term)
    
    if not results:
        update.message.reply_text(f"🤔 No results found for album: *{search_term}*", parse_mode=ParseMode.MARKDOWN)
    else:
        keyboard = []
        message = f"🎵 *Found {len(results)} songs for album '{search_term}':*\n\n"
        for i, (song_id, file_id, artist, album, title) in enumerate(results, 1):
            message += f"*{i}.* `{title}` by {artist}\n"
            # Each button's callback_data will be "dl_{song_id}"
            keyboard.append([InlineKeyboardButton(f"📥 Download No. {i}", callback_data=f"dl_{song_id}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

def search_artist(update: Update, context: CallbackContext) -> None:
    # ... (Logic to check member and parse arguments is the same) ...
    user = update.effective_user
    if not is_member(user.id): # ...
        return
    if not context.args: # ...
        return

    search_term = " ".join(context.args)
    logger.info(f"Member {user.id} is searching for artist: {search_term}")
    results = search_songs("artist", search_term)

    if not results:
        update.message.reply_text(f"🤔 No results found for artist: *{search_term}*", parse_mode=ParseMode.MARKDOWN)
    else:
        keyboard = []
        message = f"🎤 *Found {len(results)} songs by artist '{search_term}':*\n\n"
        for i, (song_id, file_id, artist, album, title) in enumerate(results, 1):
            message += f"*{i}.* `{title}` from album '{album}'\n"
            keyboard.append([InlineKeyboardButton(f"📥 Download No. {i}", callback_data=f"dl_{song_id}")])

        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

# --- NEW: Callback Query Handler for Buttons ---
def button_handler(update: Update, context: CallbackContext) -> None:
    """Download button နှိပ်လိုက်တိုင်း အလုပ်လုပ်မယ့် function"""
    query = update.callback_query
    query.answer() # Respond to the button click to remove the "loading" state
    
    user_id = query.from_user.id
    if not is_member(user_id):
        query.edit_message_text(text="🚫 Sorry, you are no longer an active member.")
        return

    callback_data = query.data
    if callback_data.startswith("dl_"):
        song_id = int(callback_data.split("_")[1])
        
        # Get file_id from database using song_id
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT file_id, title, artist FROM songs WHERE id = ?", (song_id,))
        result = cursor.fetchone()
        conn.close()

        if result:
            file_id, title, artist = result
            query.edit_message_text(text=f"⏳ Please wait, fetching download link for *{title}*...", parse_mode=ParseMode.MARKDOWN)
            
            download_link = get_download_link(file_id)
            
            if download_link:
                # Send a new message with the download link
                context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=f"✅ Here is your download link for *{title}* by *{artist}*:\n\n{download_link}\n\n_Note: This link is temporary and will expire._",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                context.bot.send_message(chat_id=query.message.chat_id, text="❌ Sorry, failed to generate a download link.")
        else:
            query.edit_message_text(text="🤔 Song not found in the database.")

def main() -> None:
    """Bot ကို Webhook mode ဖြင့် စတင် run ပေးမယ့် Main function"""
    # ... (Credential check is the same) ...

    updater = Updater(BOT_TOKEN)
    dispatcher = updater.dispatcher
    
    # Register all command handlers
    # ... (Same as before) ...
    dispatcher.add_handler(CommandHandler("s_album", search_album))
    dispatcher.add_handler(CommandHandler("s_artist", search_artist))
    
    # --- NEW: Register the Callback Query Handler for buttons ---
    dispatcher.add_handler(CallbackQueryHandler(button_handler))

    # Start the bot in webhook mode
    # ... (Same as before) ...

if __name__ == '__main__':
    main()
