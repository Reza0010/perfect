import sqlite3
from pathlib import Path

# مسیر پایگاه داده را در پوشه data تعریف می‌کنیم
DB_PATH = Path(__file__).parent.parent / "data" / "finance.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def get_db_connection():
    """ایجاد یک اتصال به پایگاه داده"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    """پایگاه داده و جداول اولیه را در صورت عدم وجود ایجاد می‌کند."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # جدول حساب‌ها
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    )
    """)

    # جدول دسته‌بندی‌ها
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    )
    """)

    # جدول تراکنش‌ها
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        amount REAL NOT NULL,
        type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
        description TEXT,
        transaction_date TEXT NOT NULL,
        account_id INTEGER,
        category_id INTEGER,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime')),
        FOREIGN KEY (account_id) REFERENCES accounts (id),
        FOREIGN KEY (category_id) REFERENCES categories (id)
    )
    """)

    # افزودن چند دسته‌بندی و حساب پیش‌فرض برای شروع
    try:
        cursor.execute("INSERT INTO categories (name) VALUES ('عمومی'), ('حقوق'), ('خرید'), ('قبوض')")
    except sqlite3.IntegrityError:
        pass # اگر از قبل وجود داشت، خطا را نادیده بگیر

    try:
        cursor.execute("INSERT INTO accounts (name) VALUES ('بانک ملت'), ('بانک سامان'), ('کیف پول')")
    except sqlite3.IntegrityError:
        pass # اگر از قبل وجود داشت، خطا را نادیده بگیر


    conn.commit()
    conn.close()
    print("پایگاه داده با موفقیت راه‌اندازی شد.")

if __name__ == '__main__':
    # این بخش فقط زمانی اجرا می‌شود که فایل مستقیماً اجرا شود
    initialize_database()