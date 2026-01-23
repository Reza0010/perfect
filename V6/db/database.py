import logging
import shutil
import os
from datetime import datetime
from pathlib import Path
from typing import Generator, List, Tuple, Dict

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError, OperationalError

from config import DATABASE_URL
from .models import Base

# تنظیمات لاگینگ
logger = logging.getLogger(__name__)

# ==============================================================================
# 1. ابزارهای کمکی و ایمنی (Backup & Path)
# ==============================================================================

def ensure_db_directory():
    """اطمینان از وجود پوشه دیتابیس و ایجاد پوشه بک‌آپ"""
    if "sqlite" in DATABASE_URL:
        # استخراج مسیر فایل
        db_path_str = DATABASE_URL.replace("sqlite:///", "")
        db_path = Path(db_path_str)
        
        # 1. ساخت پوشه دیتابیس
        if db_path.parent and not db_path.parent.exists():
            try:
                db_path.parent.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created database directory: {db_path.parent}")
            except Exception as e:
                logger.critical(f"Failed to create database directory: {e}")

        # 2. بک‌آپ گیری خودکار قبل از هر اجرا (Safety First)
        if db_path.exists():
            backup_dir = db_path.parent / "backups"
            backup_dir.mkdir(exist_ok=True)
            
            # نام فایل بک‌آپ با تاریخ و ساعت
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = backup_dir / f"startup_backup_{timestamp}.db"
            
            try:
                shutil.copy2(db_path, backup_file)
                # پاکسازی بک‌آپ‌های خیلی قدیمی (نگهداری 10 تای آخر)
                backups = sorted(backup_dir.glob("startup_backup_*.db"), key=os.path.getmtime)
                while len(backups) > 10:
                    os.remove(backups.pop(0))
                logger.info("Database backup created successfully.")
            except Exception as e:
                logger.warning(f"Failed to create startup backup: {e}")

# اجرای بررسی‌های اولیه
ensure_db_directory()

# ==============================================================================
# 2. پیکربندی موتور دیتابیس (Engine)
# ==============================================================================

# تنظیمات مخصوص SQLite برای عملکرد همزمان (Concurrency)
connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}

try:
    engine = create_engine(
        DATABASE_URL,
        connect_args=connect_args,
        pool_recycle=3600,   # بازسازی کانکشن‌ها هر یک ساعت
        pool_pre_ping=True,  # تست زنده بودن کانکشن قبل از استفاده
        echo=False           # لاگ کوئری‌ها (در پروداکشن خاموش باشد)
    )
except Exception as e:
    logger.critical(f"Failed to create database engine: {e}")
    raise

# ==============================================================================
# 3. بهینه‌سازی‌های SQLite (Performance Tuning)
# ==============================================================================

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """
    اعمال تنظیمات حیاتی برای SQLite:
    1. WAL Mode: سرعت بالا و همزمانی خواندن/نوشتن
    2. Foreign Keys: تضمین یکپارچگی داده‌ها (رابطه پدر-فرزندی)
    """
    if "sqlite" in DATABASE_URL:
        cursor = dbapi_connection.cursor()
        try:
            # فعال‌سازی محدودیت کلید خارجی (بسیار مهم برای یکپارچگی)
            cursor.execute("PRAGMA foreign_keys=ON")
            
            # فعال‌سازی حالت WAL (جلوگیری از ارور Database Locked)
            cursor.execute("PRAGMA journal_mode=WAL")
            
            # تنظیمات سرعت
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA temp_store=MEMORY")
            cursor.execute("PRAGMA mmap_size=268435456") # 256MB Cache
            cursor.execute("PRAGMA busy_timeout=10000")   # 10 ثانیه صبر برای قفل
            
        except Exception as e:
            logger.warning(f"Failed to set SQLite PRAGMA: {e}")
        finally:
            cursor.close()

# ==============================================================================
# 4. مدیریت نشست‌ها (Session Factory)
# ==============================================================================

SessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine,
    expire_on_commit=False # جلوگیری از ارور DetachedInstance در برنامه‌های Async/GUI
)

# ==============================================================================
# 5. سیستم مایگریشن هوشمند (Auto Migration)
# ==============================================================================

def _get_missing_columns_sqlite() -> List[Tuple[str, str, str]]:
    """بررسی ستون‌های جدید در مدل‌ها که در دیتابیس نیستند"""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    # تعریف اسکیما (برای آپدیت‌های آینده، این لیست را بروز نگه دارید)
    expected_schema: Dict[str, Dict[str, str]] = {
        "products": {
            "image_path": "VARCHAR(512)",
            "image_file_id": "VARCHAR(255)",
            "attributes": "TEXT",
            "related_product_ids": "VARCHAR(255)",
            "is_top_seller": "BOOLEAN DEFAULT 0",
            "discount_price": "FLOAT",  # فیلد جدید پیشنهادی
            "stock": "INTEGER DEFAULT 0"
        },
        "orders": {
            "phone_number": "VARCHAR(20)",
            "shipping_cost": "INTEGER DEFAULT 0",
            "postal_code": "VARCHAR(20)",
            "tracking_code": "VARCHAR(50)" # فیلد جدید پیشنهادی
        },
        "users": {
            "saved_address": "TEXT",
            "phone_number": "VARCHAR(20)",
            "private_note": "TEXT",
            "is_banned": "BOOLEAN DEFAULT 0",
            "last_seen": "DATETIME"
        },
        "cart_items": {
            "selected_attributes": "TEXT"
        }
    }

    missing = []
    for table, cols in expected_schema.items():
        if table not in existing_tables:
            continue

        existing_cols = {col["name"] for col in inspector.get_columns(table)}
        
        for col_name, col_type in cols.items():
            if col_name not in existing_cols:
                missing.append((table, col_name, col_type))

    return missing

def run_migrations():
    """اجرای تغییرات ساختاری روی دیتابیس بدون از دست رفتن داده"""
    if "sqlite" not in DATABASE_URL:
        return

    try:
        missing_columns = _get_missing_columns_sqlite()
        if not missing_columns:
            return

        logger.info(f"Applying {len(missing_columns)} migrations...")

        with engine.begin() as conn: # استفاده از تراکنش
            for table, column, col_type in missing_columns:
                try:
                    logger.info(f"Migrating: Adding '{column}' to '{table}'")
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                except OperationalError as e:
                    if "duplicate" not in str(e).lower():
                        logger.error(f"Migration error ({table}.{column}): {e}")
        
        logger.info("Migrations completed.")

    except Exception as e:
        logger.error(f"Migration process failed: {e}")

# ==============================================================================
# 6. راه‌اندازی و دسترسی (Public API)
# ==============================================================================

def init_db():
    """راه‌اندازی اولیه: ساخت جداول و اجرای مایگریشن"""
    try:
        # ساخت جداول اگر وجود ندارند
        Base.metadata.create_all(bind=engine)
        
        # اعمال تغییرات جدید روی جداول قدیمی
        run_migrations()
        
        logger.info("✅ Database initialized successfully.")
    except Exception as e:
        logger.critical(f"❌ Database init failed: {e}", exc_info=True)
        raise

def get_db() -> Generator[Session, None, None]:
    """تولیدکننده نشست دیتابیس (Context Manager)"""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()