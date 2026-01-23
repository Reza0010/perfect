import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from dotenv import load_dotenv

# ==============================================================================
# 1. تنظیمات مسیرها (Paths)
# ==============================================================================
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / '.env'

# بارگذاری متغیرهای محیطی (اگر قبلاً ست نشده باشند)
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH, override=False)

# مسیرهای فایل‌های استاتیک و مدیا
MEDIA_DIR = BASE_DIR / 'media'
MEDIA_PRODUCTS_DIR = MEDIA_DIR / 'products'
TEMP_DIR = BASE_DIR / 'temp' # برای فایل‌های موقت

# مسیرهای دیتابیس و لاگ
DB_FOLDER = BASE_DIR / 'db'
BACKUP_DIR = DB_FOLDER / 'backups'
LOG_DIR = BASE_DIR / 'logs'

# لیست پوشه‌هایی که باید وجود داشته باشند
REQUIRED_DIRS = [
    MEDIA_DIR, 
    MEDIA_PRODUCTS_DIR, 
    DB_FOLDER, 
    BACKUP_DIR, 
    LOG_DIR,
    TEMP_DIR
]

# ساخت خودکار پوشه‌ها
for folder in REQUIRED_DIRS:
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        print(f"❌ Error: Permission denied creating directory: {folder}")
        sys.exit(1)

# ==============================================================================
# 2. پیکربندی لاگینگ (Advanced Logging)
# ==============================================================================
def setup_logging():
    """پیکربندی سیستم لاگینگ با قابلیت چرخش فایل و خروجی رنگی"""
    
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    
    # فرمت استاندارد
    log_format = '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # تلاش برای استفاده از لاگ رنگی در کنسول
    try:
        import colorlog
        console_formatter = colorlog.ColoredFormatter(
            "%(log_color)s" + log_format,
            datefmt=date_format,
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
        )
    except ImportError:
        console_formatter = logging.Formatter(log_format, datefmt=date_format)

    file_formatter = logging.Formatter(log_format, datefmt=date_format)
    
    # فایل لاگ با چرخش (حداکثر 10MB، نگهداری 5 فایل)
    log_file = LOG_DIR / 'app.log'
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'
    )
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(log_level)
    
    # کنسول
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(log_level)
    
    # تنظیمات ریشه
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # جلوگیری از تکرار هندلرها (در صورت ریلود ماژول)
    if not root_logger.hasHandlers():
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
    
    # سایلنت کردن کتابخانه‌های پرحرف
    for lib in ["httpx", "telegram", "apscheduler", "sqlalchemy", "PIL"]:
        logging.getLogger(lib).setLevel(logging.WARNING)

setup_logging()
logger = logging.getLogger("Config")

# ==============================================================================
# 3. تنظیمات ربات و ادمین (Bot & Admin)
# ==============================================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_BOT_TOKEN:
    logger.critical("⛔ TELEGRAM_BOT_TOKEN is missing! The bot cannot start.")
    # می‌توان اینجا برنامه را متوقف کرد اگر توکن حیاتی است
    # sys.exit(1)

# ادمین‌ها
ADMIN_USER_IDS_STR = os.getenv("ADMIN_USER_IDS", "")
try:
    ADMIN_USER_IDS = [int(x.strip()) for x in ADMIN_USER_IDS_STR.split(',') if x.strip().isdigit()]
except Exception as e:
    logger.error(f"Error parsing ADMIN_USER_IDS: {e}")
    ADMIN_USER_IDS = []

if not ADMIN_USER_IDS:
    logger.warning("⚠️ No admins defined! Some features may be restricted.")

# ==============================================================================
# 4. تنظیمات دیتابیس (Database)
# ==============================================================================
DB_NAME = 'shop_bot.db'
# پشتیبانی از دیتابیس‌های ابری (مثل PostgreSQL)
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # استفاده از SQLite محلی
    DATABASE_URL = f"sqlite:///{DB_FOLDER / DB_NAME}"
    logger.info(f"Using SQLite database at: {DB_FOLDER / DB_NAME}")
else:
    # اصلاح URL برای SQLAlchemy (اگر postgres:// بود تبدیل به postgresql:// شود)
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    logger.info("Using External Database")

# ==============================================================================
# 5. تنظیمات اضافی (Misc)
# ==============================================================================
# منطقه زمانی پیش‌فرض
TIME_ZONE = os.getenv("TIME_ZONE", "Asia/Tehran")

# خروجی نهایی
__all__ = [
    "BASE_DIR", "MEDIA_DIR", "MEDIA_PRODUCTS_DIR", "TEMP_DIR",
    "DB_FOLDER", "BACKUP_DIR", "LOG_DIR",
    "TELEGRAM_BOT_TOKEN", "ADMIN_USER_IDS", 
    "DATABASE_URL", "TIME_ZONE"
]