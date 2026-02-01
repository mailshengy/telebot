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
TIMEZONE = "Asia/Singapore"

# --- LOGGING ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# --- DATABASE SETUP ---
def init_db():
    conn = psycopg2.connect(DB_URL)
    c = conn.cursor()
    
    # 1. Table for Members
    c.execute("""
        CREATE TABLE IF NOT EXISTS members (
            user_id BIGINT PRIMARY KEY,
            chat_id BIGINT,
            full_name TEXT,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 2. Table for State (Remembering whose turn it is)
    c.execute("""
        CREATE TABLE IF NOT EXISTS bot_state (
            id INTEGER PRIMARY KEY,
            current_index INTEGER
        )
    """)
    
    # Initialize state if empty
    c.execute("INSERT INTO bot_state (id, current_index) VALUES (1, -1) ON CONFLICT (id) DO NOTHING")
    
    conn.commit()
    conn.close()

def add_user(user_id, chat_id, full_name):
    conn = psycopg2.connect(DB_URL)
    c = conn.cursor()
    c.execute("""
        INSERT INTO members (user_id, chat_id, full_name)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET full_name = EXCLUDED.full_name, chat_id = EXCLUDED.chat_id
    """, (user_id, chat_id, full_name))
    conn.commit()
    conn.close()

def get_rotation_info():
    """Fetches all members and the current index state."""
    conn = psycopg2.connect(DB_URL)
    c = conn.cursor()
    
    # Get all members sorted by join time (or user_id) so the order is stable
    c.execute("SELECT chat_id, full_name FROM members ORDER BY joined_at ASC, user_id ASC")
    members = c.fetchall()
    
    # Get last index
    c.execute("SELECT current_index FROM bot_state WHERE id = 1")
    current_index = c.fetchone()[0]
    
    conn.close()
    return members, current_index

def update_index(new_index):
    """Saves the new index to the DB."""
    conn = psycopg2.connect(DB_URL)
    c = conn.cursor()
    c.execute("UPDATE bot_state SET current_index = %s WHERE id = 1", (new_index,))
    conn.commit()
    conn.close()

# --- BOT COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Thankful Bot is Online! Type /join to enter the rotation.")

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    try:
        add_user(user.id, chat.id, user.full_name)
        await update.message.reply_text(f"✅ {user.full_name}, you have been added to the rotation!")
    except Exception as e:
        logging.error(f"DB Error: {e}")
        await update.message.reply_text("❌ Error joining database.")

# --- ROTATION LOGIC ---
async def send_reminders(context: ContextTypes.DEFAULT_TYPE):
    members, last_index = get_rotation_info()
    
    if not members:
        logging.warning("No members in rotation.")
        return

    # Calculate next person
    # logic: next_index = (last_index + 1) % total_members
    # The '%' (modulo) operator makes it loop back to 0 automatically when it reaches the end.
    next_index = (last_index + 1) % len(members)
    
    # Get the lucky person
    chat_id, name = members[next_index]
    
    logging.info(f"It is {name}'s turn (Index: {next_index})")

    try:
        # Send message to the specific person
        msg = f"Hey {name}, reminder to share any thanksgiving or devotions for the day! 🌞"
        await context.bot.send_message(chat_id=chat_id, text=msg)
        
        # ALSO: Send a message to the group if you want everyone to know?
        # If you want to notify the whole group who is on duty, you need the Group Chat ID.
        # For now, this sends to the individual's private chat or the group where they typed /join.
        
        # Save the new state so tomorrow we pick the next person
        update_index(next_index)
        
    except Exception as e:
        logging.error(f"Failed to send to {name}: {e}")

# --- TEST COMMAND ---
async def test_rotation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually triggers the rotation to see who is next."""
    await update.message.reply_text("🔄 Testing Rotation...")
    await send_reminders(context)

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    init_db()

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("join", join))
    application.add_handler(CommandHandler("test", test_rotation))

    tz = pytz.timezone(TIMEZONE)
    target_time = datetime.time(hour=8, minute=0, second=0, tzinfo=tz)
    
    job_queue = application.job_queue
    job_queue.run_daily(send_reminders, time=target_time)
    
    application.run_polling()
