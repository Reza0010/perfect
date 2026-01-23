import sys
import os
import asyncio
import logging
import warnings
from pathlib import Path

# --- تنظیمات محیطی ---
os.environ["QT_FONT_DPI"] = "96"
os.environ["QT_LOGGING_RULES"] = "qt.qpa.screen=false"

from telegram.warnings import PTBUserWarning
warnings.filterwarnings("ignore", category=PTBUserWarning)

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# ایمپورت‌های پروژه
from config import TELEGRAM_BOT_TOKEN, ADMIN_USER_IDS, LOG_DIR
from db.database import init_db
from db import crud
from bot.loader import setup_application_handlers
from bot.utils import run_db

try:
    from PyQt6.QtWidgets import QApplication, QSplashScreen
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QFont, QPixmap, QColor, QPainter
    import qasync
    import qtawesome as qta
    
    from admin_panel.main_window import MainWindow
    from telegram import Update
    from telegram.ext import Application
except ImportError as e:
    print(f"❌ Error: {e}")
    sys.exit(1)

# لاگینگ
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "app_startup.log", encoding='utf-8')
    ]
)
# سایلنت کردن کتابخانه‌ها
for lib in ["httpx", "telegram", "apscheduler", "sqlalchemy", "qasync", "matplotlib"]:
    logging.getLogger(lib).setLevel(logging.WARNING)

logger = logging.getLogger("Launcher")

# ====================================================================
# 1. کلاس اسپلش اسکرین
# ====================================================================
class LoadingSplash(QSplashScreen):
    def __init__(self):
        self.width, self.height = 450, 300
        pixmap = QPixmap(self.width, self.height)
        pixmap.fill(QColor("#16161a"))
        
        painter = QPainter()
        if painter.begin(pixmap):
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QColor("#7f5af0"))
            painter.drawRect(0, 0, self.width-1, self.height-1)
            painter.setPen(QColor("white"))
            font_title = QFont("Segoe UI", 24, QFont.Weight.Bold)
            painter.setFont(font_title)
            painter.drawText(0, 60, self.width, 50, Qt.AlignmentFlag.AlignCenter, "Telegram Shop")
            font_sub = QFont("Segoe UI", 12)
            painter.setFont(font_sub)
            painter.setPen(QColor("#94a1b2"))
            painter.drawText(0, 110, self.width, 30, Qt.AlignmentFlag.AlignCenter, "Management Panel")
            try:
                icon = qta.icon('fa5s.store', color='#7f5af0')
                icon.paint(painter, (self.width - 64) // 2, 150, 64, 64)
            except: pass
            painter.end()
        
        super().__init__(pixmap)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)

    def show_message(self, message):
        self.showMessage(
            f"\n\n\n\n\n\n\n\n\n{message}", 
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter, 
            QColor("#2cb67d")
        )
        QApplication.processEvents()

# ====================================================================
# 2. هندلر ادمین
# ====================================================================
async def admin_quick_action_handler(update: Update, context):
    if not update.callback_query: return
    query = update.callback_query
    
    if query.from_user.id not in ADMIN_USER_IDS:
        await query.answer("⛔ دسترسی ندارید", show_alert=True)
        return

    try:
        data = query.data.split(':')
        if len(data) < 2: return
        action, order_id = data[0], int(data[1])
        
        status_map = {"adm_approve": "approved", "adm_ship": "shipped", "adm_reject": "rejected"}
        new_status = status_map.get(action)
        
        if new_status:
            order = await run_db(crud.update_order_status, order_id, new_status)
            if order:
                await query.answer(f"سفارش #{order_id} آپدیت شد.")
                try:
                    curr = query.message.caption_html or ""
                    await query.edit_message_caption(caption=f"{curr}\n\n✅ وضعیت: {new_status}", parse_mode='HTML')
                except: pass
    except Exception as e:
        logger.error(f"Admin Action Error: {e}")

# ====================================================================
# 3. استارتاپ منیجر (Startup Manager)
# ====================================================================
class ApplicationManager:
    def __init__(self, app, splash, loop):
        self.app = app
        self.splash = splash
        self.loop = loop
        self.bot_app = None
        self.window = None

    async def start(self):
        """مراحل راه‌اندازی (اجرا به عنوان Task)"""
        
        # 1. دیتابیس
        self.splash.show_message("اتصال به دیتابیس...")
        await asyncio.sleep(0.1) # تنفس به GUI
        try:
            await self.loop.run_in_executor(None, init_db)
        except Exception as e:
            logger.error(f"DB Error: {e}")

        # 2. تلگرام
        is_bot_online = False
        if TELEGRAM_BOT_TOKEN:
            self.splash.show_message("اتصال به تلگرام...")
            try:
                bot_builder = Application.builder().token(TELEGRAM_BOT_TOKEN)
                # تایم‌اوت اتصال را کم می‌کنیم تا برنامه فریز نشود
                self.bot_app = bot_builder.build()
                setup_application_handlers(self.bot_app, admin_handler=admin_quick_action_handler)
                
                await self.bot_app.initialize()
                await self.bot_app.start()
                
                # تست اتصال واقعی
                me = await self.bot_app.bot.get_me()
                self.splash.show_message(f"متصل شد: {me.first_name}")
                
                await self.bot_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
                is_bot_online = True
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Bot Connection Failed: {e}")
                self.splash.show_message("خطا در اتصال ربات! (حالت آفلاین)")
                is_bot_online = False
                self.bot_app = None # مهم: اگر وصل نشد، نال کنیم
                await asyncio.sleep(1.5)
        else:
            self.splash.show_message("حالت آفلاین (بدون توکن)")
            await asyncio.sleep(0.5)

        # 3. GUI
        self.splash.show_message("راه‌اندازی پنل...")
        await asyncio.sleep(0.1)
        
        self.window = MainWindow(bot_application=self.bot_app if is_bot_online else None)
        
        # تنظیم دقیق وضعیت اتصال
        if hasattr(self.window, 'status_label'):
            if is_bot_online:
                self.window.status_label.setText("🟢 آنلاین")
                self.window.status_label.setStyleSheet("color: #2cb67d; font-weight: bold;")
            else:
                self.window.status_label.setText("🔴 آفلاین")
                self.window.status_label.setStyleSheet("color: #ef4565; font-weight: bold;")

        self.splash.finish(self.window)
        self.window.show()

    async def shutdown(self):
        """خروج ایمن"""
        logger.info("Shutting down...")
        if self.bot_app:
            try:
                if self.bot_app.updater.running: await self.bot_app.updater.stop()
                if self.bot_app.running: await self.bot_app.stop()
                await self.bot_app.shutdown()
            except: pass
        self.loop.stop()

# ====================================================================
# 4. Main Entry Point
# ====================================================================
def main():
    if hasattr(Qt.ApplicationAttribute, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(Qt.ApplicationAttribute, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Shop Admin")
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    font = QFont("Segoe UI", 10)
    app.setFont(font)

    splash = LoadingSplash()
    splash.show()

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    manager = ApplicationManager(app, splash, loop)

    # shutdown امن
    app.lastWindowClosed.connect(
        lambda: loop.create_task(manager.shutdown())
    )

    # ✅ اجرای صحیح استارتاپ
    loop.create_task(manager.start())

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"Loop Error: {e}")

if __name__ == "__main__":
    main()