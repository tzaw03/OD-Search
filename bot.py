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
# Webhook အတွက် Railway/Zeabur ကပေးမယ့် URL ကို ဒီမှာထည့်ရပါမယ်
WEBHOOK_URL = os.getenv("WEBHOOK_URL") 

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

def is_member(user_id: int) -> bool:
    """User ID ကို စစ်ဆေးပြီး သက်တမ်းရှိတဲ့ member ဟုတ်မဟုတ် စစ်ဆေးပေးသည်"""
    # ... (ဒီ function က အရင်အတိုင်းပါပဲ၊ ပြောင်းလဲရန်မလိုပါ) ...
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

def start(update: Update, context: CallbackContext) -> None:
    """User က /start လို့ရိုက်လိုက်ရင် အလုပ်လုပ်မယ့် function"""
    # ... (ဒီ function က အရင်အတိုင်းပါပဲ၊ ပြောင်းလဲရန်မလိုပါ) ...
    user = update.effective_user
    user_id = user.id
    logger.info(f"🚀 User {user.first_name} ({user_id}) started the bot.")
    if is_member(user_id):
        update.message.reply_text(f"👋 Welcome back, {user.first_name}!\n\n✨ You are an active member. You can start searching for music.")
    else:
        update.message.reply_text(f"🚫 Sorry, {user.first_name}.\n\nYou are not an authorized member of this bot.")

def add_member(update: Update, context: CallbackContext) -> None:
    """Admin က member အသစ်ထည့်ရန် command"""
    # ... (ဒီ function က အရင်အတိုင်းပါပဲ၊ ပြောင်းလဲရန်မလိုပါ) ...
    admin = update.effective_user
    if admin.id != ADMIN_USER_ID:
        update.message.reply_text("🚫 Sorry, this is an admin-only command.")
        return
    if not context.args or len(context.args) > 2:
        update.message.reply_text("✍️ Usage: `/add_member <user_id> [days]`\nExample: `/add_member 12345678 30`")
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
        cursor.execute("""
            INSERT INTO members (telegram_id, expiry_date, status, first_name)
            VALUES (?, ?, 'active', 'N/A')
            ON CONFLICT(telegram_id) DO UPDATE SET
                expiry_date = excluded.expiry_date,
                status = 'active';
        """, (target_user_id, expiry_date))
        conn.commit()
        conn.close()
        expiry_date_str = expiry_date.strftime('%Y-%m-%d')
        update.message.reply_text(
            f"✅ Success!\nUser `{target_user_id}` is now an active member.\nMembership is valid until: *{expiry_date_str}* ({days_to_add} days).",
            parse_mode=ParseMode.MARKDOWN
        )
        logger.info(f"Admin ({admin.id}) added/updated user {target_user_id} for {days_to_add} days.")
    except Exception as e:
        logger.error(f"Database error in add_member: {e}")
        update.message.reply_text(f"❌ An error occurred while updating the database.")


def main() -> None:
    """Bot ကို Webhook mode ဖြင့် စတင် run ပေးမယ့် Main function"""
    if not BOT_TOKEN or not WEBHOOK_URL:
        logger.error("❌ BOT_TOKEN and WEBHOOK_URL secrets must be set!")
        return

    updater = Updater(BOT_TOKEN)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("add_member", add_member))

    # Railway/Zeabur က သတ်မှတ်ပေးတဲ့ PORT ကိုရယူခြင်း
    PORT = int(os.environ.get('PORT', '8443'))
    
    # Webhook ကို စတင်ခြင်း
    updater.start_webhook(listen="0.0.0.0",
                          port=PORT,
                          url_path=BOT_TOKEN,
                          webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
                          
    logger.info(f"✅ Bot has started on webhook mode, listening on port {PORT}.")
    updater.idle()

if __name__ == '__main__':
    main()
