import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import logging
from datetime import datetime, time, timedelta
import re

# Bot tokenini Telegramdan olingan token bilan almashtiring
TOKEN = '7485902568:AAHbZHsXOrn2Gs-xllcjf_c3x0nXhn_O2UE'

# Admin paroli
ADMIN_PASSWORD = 'admin123'

# Loggerni sozlash
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Reklama o'chirilmaydigan vaqt oralig'lari
ad_free_times = [(time(10, 0), time(11, 0)), (time(22, 0), time(23, 0))]

# Ma'lumotlar bazasini sozlash
def create_tables():
    with sqlite3.connect('bot_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS offensive_words (id INTEGER PRIMARY KEY, word TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS ad_keywords (id INTEGER PRIMARY KEY, keyword TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS admins (id INTEGER PRIMARY KEY, user_id INTEGER)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS sent_ads (id INTEGER PRIMARY KEY, user_id INTEGER, timestamp DATETIME)''')
        conn.commit()

create_tables()

# Ma'lumotlar bazasidan so'zlar va adminlarni olish
def get_offensive_words():
    with sqlite3.connect('bot_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT word FROM offensive_words")
        return [row[0] for row in cursor.fetchall()]

def get_ad_keywords():
    with sqlite3.connect('bot_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT keyword FROM ad_keywords")
        return [row[0] for row in cursor.fetchall()]

def get_admins():
    with sqlite3.connect('bot_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM admins")
        return [row[0] for row in cursor.fetchall()]

# Ma'lumotlar bazasiga so'zlar va adminlarni qo'shish
def add_offensive_word_db(word):
    with sqlite3.connect('bot_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO offensive_words (word) VALUES (?)", (word,))
        conn.commit()

def add_ad_keyword_db(keyword):
    with sqlite3.connect('bot_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO ad_keywords (keyword) VALUES (?)", (keyword,))
        conn.commit()

def add_admin_db(user_id):
    with sqlite3.connect('bot_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO admins (user_id) VALUES (?)", (user_id,))
        conn.commit()

# Ma'lumotlar bazasidan so'zlarni o'chirish
def remove_offensive_word_db(word):
    with sqlite3.connect('bot_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM offensive_words WHERE word = ?", (word,))
        conn.commit()

def remove_ad_keyword_db(keyword):
    with sqlite3.connect('bot_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ad_keywords WHERE keyword = ?", (keyword,))
        conn.commit()

# Reklama yuborilganligini tekshirish va qo'shish
def has_sent_ad_recently(user_id):
    current_time = datetime.now()
    for start, end in ad_free_times:
        if start <= current_time.time() <= end:
            with sqlite3.connect('bot_data.db') as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT timestamp FROM sent_ads WHERE user_id = ? AND timestamp BETWEEN ? AND ?",
                    (
                        user_id,
                        current_time.replace(hour=start.hour, minute=start.minute),
                        current_time.replace(hour=end.hour, minute=end.minute),
                    ),
                )
                if cursor.fetchone():
                    return True
    return False

def add_sent_ad(user_id):
    with sqlite3.connect('bot_data.db') as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO sent_ads (user_id, timestamp) VALUES (?, ?)",
            (user_id, datetime.now()),
        )
        conn.commit()

# Havolalarni tekshirish va o'chirish
def clean_links(text):
    url_pattern = re.compile(
        r'(?P<url>https?://[^\s]+)|(www\.[^\s]+)'
    )
    urls = url_pattern.findall(text)
    cleaned_text = text
    for url in urls:
        full_url = url[0] or url[1]
        if full_url and not re.search(r'(youtube\.com|youtu\.be)', full_url):
            cleaned_text = cleaned_text.replace(full_url, '')
    return cleaned_text

# Foydalanuvchi guruh admini yoki yo'qligini tekshirish
async def is_group_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_admins = await context.bot.get_chat_administrators(update.message.chat_id)
    return any(admin.user.id == update.message.from_user.id for admin in chat_admins)

# Haqoratli so'zlarni aniqlash
def detect_offensive_words(text):
    offensive_words = get_offensive_words()
    for word in offensive_words:
        if re.search(r'\b' + re.escape(word) + r'\b', text):
            return True
    return False

# Guruhda kelayotgan xabarlarni tekshirish
async def check_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        is_admin = await is_group_admin(update, context)
        
        text = update.message.text.lower()
        ad_keywords = get_ad_keywords()

        if detect_offensive_words(text):
            await update.message.delete()
            return

        if any(keyword in text for keyword in ad_keywords):
            if has_sent_ad_recently(user_id) and not is_admin:
                await update.message.delete()
            else:
                add_sent_ad(user_id)

        if not is_admin:
            cleaned_text = clean_links(update.message.text)
            if cleaned_text != update.message.text:
                await update.message.delete()

    except Exception as e:
        logger.error(f"Error in check_message: {e}", exc_info=True)

# Haqoratli so'zlarni qo'shish
async def add_offensive_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id in get_admins():
        new_word = " ".join(context.args).lower()
        add_offensive_word_db(new_word)
        await update.message.reply_text(f"Yangi haqoratli so'z qo'shildi: {new_word}")
    else:
        await update.message.reply_text("Siz admin emassiz!")

# Reklama so'zlarni qo'shish
async def add_ad_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id in get_admins():
        new_ad = " ".join(context.args).lower()
        add_ad_keyword_db(new_ad)
        await update.message.reply_text(f"Yangi reklama qo'shildi: {new_ad}")
    else:
        await update.message.reply_text("Siz admin emassiz!")

# Haqoratli so'zlarni o'chirish
async def remove_offensive_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id in get_admins():
        word = " ".join(context.args).lower()
        remove_offensive_word_db(word)
        await update.message.reply_text(f"Haqoratli so'z o'chirildi: {word}")
    else:
        await update.message.reply_text("Siz admin emassiz!")

# Reklama so'zlarni o'chirish
async def remove_ad_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id in get_admins():
        keyword = " ".join(context.args).lower()
        remove_ad_keyword_db(keyword)
        await update.message.reply_text(f"Reklama o'chirildi: {keyword}")
    else:
        await update.message.reply_text("Siz admin emassiz!")

# Reklamalar ro'yxatini ko'rsatish
async def show_ad_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    if from_callback:
        user_id = update.callback_query.from_user.id
        message = update.callback_query.message
    else:
        user_id = update.message.from_user.id
        message = update.message
    if user_id in get_admins():
        ad_keywords = get_ad_keywords()
        ad_list = '\n'.join(ad_keywords)
        if not ad_list:
            ad_list = "Hech qanday reklama so'zi qo'shilmagan."
        await message.reply_text(f"Reklama so'zlari ro'yxati:\n{ad_list}")
    else:
        await message.reply_text("Siz admin emassiz!")

# Haqoratli so'zlar ro'yxatini ko'rsatish
async def show_offensive_words(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    if from_callback:
        user_id = update.callback_query.from_user.id
        message = update.callback_query.message
    else:
        user_id = update.message.from_user.id
        message = update.message
    if user_id in get_admins():
        offensive_words = get_offensive_words()
        word_list = '\n'.join(offensive_words)
        if not word_list:
            word_list = "Hech qanday haqoratli so'z qo'shilmagan."
        await message.reply_text(f"Haqoratli so'zlar ro'yxati:\n{word_list}")
    else:
        await message.reply_text("Siz admin emassiz!")

# Adminni tasdiqlash
async def verify_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if context.args and context.args[0] == ADMIN_PASSWORD:
        add_admin_db(user_id)
        await update.message.reply_text("Siz admin sifatida tasdiqlandingiz!")
    else:
        await update.message.reply_text("Noto'g'ri parol!")

# Admin panelini ko'rsatish
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id in get_admins():
        keyboard = [
            [InlineKeyboardButton("Reklama so'zlarini ko'rish", callback_data='show_ads')],
            [InlineKeyboardButton("Haqoratli so'zlarni ko'rish", callback_data='show_words')],
            [InlineKeyboardButton("Yangi reklama qo'shish", callback_data='add_ad')],
            [InlineKeyboardButton("Yangi haqoratli so'z qo'shish", callback_data='add_word')],
            [InlineKeyboardButton("Reklamani o'chirish", callback_data='remove_ad')],
            [InlineKeyboardButton("Haqoratli so'zni o'chirish", callback_data='remove_word')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Admin paneli:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Siz admin emassiz!")

# Admin panel callback-larini boshqarish
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == 'show_ads':
        await show_ad_keywords(update, context, from_callback=True)
    elif query.data == 'show_words':
        await show_offensive_words(update, context, from_callback=True)
    elif query.data == 'add_ad':
        await query.message.reply_text("Yangi reklama qo'shish uchun /addad komandasi bilan yangi reklama so'zlarini kiriting.")
    elif query.data == 'add_word':
        await query.message.reply_text("Yangi haqoratli so'z qo'shish uchun /addword komandasi bilan yangi so'zlarni kiriting.")
    elif query.data == 'remove_ad':
        await query.message.reply_text("Reklamani o'chirish uchun /removead komandasi bilan reklama so'zini kiriting.")
    elif query.data == 'remove_word':
        await query.message.reply_text("Haqoratli so'zni o'chirish uchun /removeword komandasi bilan so'zni kiriting.")

# Boshlang'ich xabar
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Salom! Men guruhdagi haqoratli so'zlarni va reklamalarni boshqaradigan botiman.")

def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('addword', add_offensive_word))
    application.add_handler(CommandHandler('addad', add_ad_keyword))
    application.add_handler(CommandHandler('removeword', remove_offensive_word))
    application.add_handler(CommandHandler('removead', remove_ad_keyword))
    application.add_handler(CommandHandler('showads', show_ad_keywords))
    application.add_handler(CommandHandler('showwords', show_offensive_words))
    application.add_handler(CommandHandler('verifyadmin', verify_admin))
    application.add_handler(CommandHandler('adminpanel', admin_panel))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), check_message))
    application.add_handler(CallbackQueryHandler(button_handler))

    application.run_polling()

if __name__ == '__main__':
    main()
