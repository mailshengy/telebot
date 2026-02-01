import os
import logging
import psycopg2
import pytz
import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- CONFIGURATION ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
DB_URL = os.getenv("DATABASE_URL")
# Change this string to your local timezone (e.g., 'America/New_York', 'Europe/London')
TIMEZONE = "Asia/Singapore" 

# --- LOGGING ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# --- DATABASE SETUP ---
def init_db():
    """Create the table if it doesn't exist."""
    conn = psycopg2.connect(DB_URL)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS members (
            user_id BIGINT PRIMARY KEY,
            chat_id BIGINT,
            full_name TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_user(user_id, chat_id, full_name):
    """Save or update user details."""
    conn = psycopg2.connect(DB_URL)
    c = conn.cursor()
    c.execute("""
        INSERT INTO members (user_id, chat_id, full_name)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET full_name = EXCLUDED.full_name, chat_id = EXCLUDED.chat_id
    """, (user_id, chat_id, full_name))
    conn.commit()
    conn.close()

def get_all_members():
    """Fetch all subscribers."""
    conn = psycopg2.connect(DB_URL)
    c = conn.cursor()
    c.execute("SELECT chat_id, full_name FROM members")
    rows = c.fetchall()
    conn.close()
    return rows

# --- BOT COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Thankful Bot is Online! Type /join to get daily reminders.")

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    try:
        add_user(user.id, chat.id, user.full_name)
        await update.message.reply_text(f"✅ {user.full_name}, you are added to the reminder list!")
    except Exception as e:
        logging.error(f"DB Error: {e}")
        await update.message.reply_text("❌ Error joining database.")

# --- DAILY TASK ---
async def send_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Sends the daily message to all users."""
    members = get_all_members()
    logging.info(f"Sending reminders to {len(members)} users...")
    
    for chat_id, name in members:
        try:
            # The exact message you wanted
            msg = f"{name}, reminder to share any thanksgiving or devotions for the day! 🌞"
            await context.bot.send_message(chat_id=chat_id, text=msg)
        except Exception as e:
            logging.error(f"Failed to send to {name}: {e}")

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    # 1. Initialize DB
    init_db()

    # 2. Build App
    application = Application.builder().token(TOKEN).build()

    # 3. Add Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("join", join))

    # 4. Schedule Job
    # We define the specific time zone
    tz = pytz.timezone(TIMEZONE)
    # Set the time (e.g., 8:00 AM)
    target_time = datetime.time(hour=8, minute=0, second=0, tzinfo=tz)
    
    job_queue = application.job_queue
    job_queue.run_daily(send_reminders, time=target_time)
    
    logging.info(f"Bot started. Reminders scheduled for 8:00 AM {TIMEZONE}")

    # 5. Run Forever
    application.run_polling()
