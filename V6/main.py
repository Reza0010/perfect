import logging
import sys
import os
import warnings
import time
from pathlib import Path

from telegram import Update
from telegram.ext import Application, Defaults
from telegram.constants import ParseMode
from telegram.warnings import PTBUserWarning

# نادیده گرفتن هشدارهای غیرمهم تلگرام
warnings.filterwarnings("ignore", category=PTBUserWarning)

# افزودن مسیر پروژه به سیستم
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# ایمپورت ماژول‌های پروژه
from config import TELEGRAM_BOT_TOKEN, LOG_DIR
from db.database import init_db
from bot.loader import setup_application_handlers

# پیکربندی سیستم لاگینگ (فایل + کنسول)
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(), # خروجی کنسول
        logging.FileHandler(LOG_DIR / "bot_standalone.log", encoding='utf-8') # خروجی فایل
    ]
)
# کاهش نویز لاگ‌های کتابخانه‌های جانبی
for lib in ["httpx", "telegram", "apscheduler", "sqlalchemy"]:
    logging.getLogger(lib).setLevel(logging.WARNING)

logger = logging.getLogger("BotLauncher")

def print_banner():
    """نمایش لوگوی متنی در شروع"""
    banner = r"""
    ====================================================
      ____  _                 ____        _   
     / ___|| |__   ___  _ __ | __ )  ___ | |_ 
     \___ \| '_ \ / _ \| '_ \|  _ \ / _ \| __|
      ___) | | | | (_) | |_) | |_) | (_) | |_ 
     |____/|_| |_|\___/| .__/|____/ \___/ \__|
                       |_|                    
    ====================================================
    🚀 Telegram Shop Bot - Standalone Mode
    📌 Version: 5.0.0
    ====================================================
    """
    print(banner)

def main():
    """
    نقطه شروع اجرای ربات به صورت مستقل (CLI Mode).
    """
    print_banner()
    logger.info("Initializing system...")

    # 1. بررسی محیط
    env_path = BASE_DIR / '.env'
    if not env_path.exists():
        logger.warning("⚠️  .env file not found! Using system environment variables.")

    if not TELEGRAM_BOT_TOKEN:
        logger.critical("⛔ Error: TELEGRAM_BOT_TOKEN is missing. Please check your config.")
        sys.exit(1)

    # 2. راه‌اندازی دیتابیس
    try:
        logger.info("Connecting to database...")
        init_db()
        logger.info("✅ Database connected successfully.")
    except Exception as e:
        logger.critical(f"❌ Database Initialization Failed: {e}")
        sys.exit(1)

    # 3. ساخت و اجرای ربات
    try:
        logger.info("Building Bot Application...")
        
        # تنظیمات پیش‌فرض (مثلاً پارس مود HTML برای همه پیام‌ها)
        defaults = Defaults(parse_mode=ParseMode.HTML)
        
        app = Application.builder() \
            .token(TELEGRAM_BOT_TOKEN) \
            .defaults(defaults) \
            .build()
        
        # افزودن هندلرها
        setup_application_handlers(app)
        
        # 4. شروع عملیات
        logger.info("✅ Bot is ready! Starting polling...")
        print("\n🟢 Bot is running... Press Ctrl+C to stop.\n")
        
        # اجرای ربات (Blocking)
        app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True # نادیده گرفتن آپدیت‌های قدیمی در استارت (اختیاری)
        )
        
    except Exception as e:
        logger.critical(f"❌ Critical Error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user. Goodbye!")
        sys.exit(0)