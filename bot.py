import os
import sqlite3
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

# --- Configuration ---
# GitHub Secrets ကနေ credentials တွေကိုဖတ်ရန်ပြင်ဆင်ခြင်း
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID")) # သင့်ရဲ့ Telegram ID ကို Secret မှာထည့်ရပါမယ်
DB_FILE = "music_bot.db"

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

def is_member(user_id: int) -> bool:
    """User ID ကို စစ်ဆေးပြီး သက်တမ်းရှိတဲ့ member ဟုတ်မဟုတ် စစ်ဆေးပေးသည်"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # User ကို members table ထဲမှာ Telegram ID နဲ့ ရှာပါမယ်
    cursor.execute("SELECT expiry_date, status FROM members WHERE telegram_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()

    if result:
        expiry_date_str, status = result
        # Handle different datetime formats that might be stored
        try:
            # For ISO format with microseconds
            expiry_date = datetime.fromisoformat(expiry_date_str)
        except ValueError:
            # For format like 'YYYY-MM-DD HH:MM:SS'
            expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d %H:%M:%S')
        
        # Status က 'active' ဖြစ်ပြီး သက်တမ်းမကုန်သေးရင် True ပြန်ပါမယ်
        if status == 'active' and expiry_date > datetime.now():
            return True
            
    return False

def start(update: Update, context: CallbackContext) -> None:
    """User က /start လို့ရိုက်လိုက်ရင် အလုပ်လုပ်မယ့် function"""
    user = update.effective_user
    user_id = user.id

    logger.info(f"🚀 User {user.first_name} ({user_id}) started the bot.")

    if is_member(user_id):
        # Emoji များဖြင့် ပြန်စာကိုပြင်ဆင်ထားသည်
        update.message.reply_text(f"👋 Welcome back, {user.first_name}!\n\n✨ You are an active member. You can start searching for music.")
    else:
        # Emoji များဖြင့် ပြန်စာကိုပြင်ဆင်ထားသည်
        update.message.reply_text(f"🚫 Sorry, {user.first_name}.\n\nYou are not an authorized member of this bot.")

# TODO: Add admin commands (/add_member, /ban, /unban)
# TODO: Add user commands (/s_album, /s_artist)

def main() -> None:
    """Bot ကို စတင် run ပေးမယ့် Main function"""
    if not BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN secret is not set!")
        return

    updater = Updater(BOT_TOKEN)
    dispatcher = updater.dispatcher

    # Command handlers တွေကို ထည့်သွင်းခြင်း
    dispatcher.add_handler(CommandHandler("start", start))

    # Bot ကို စတင်ခြင်း
    updater.start_polling()
    logger.info("✅ Bot has started polling.")
    updater.idle()

if __name__ == '__main__':
    main()
