import sys
import asyncio
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QStackedWidget, QFrame, QButtonGroup, QLabel, QGraphicsDropShadowEffect,
    QSizePolicy
)
from PyQt6.QtCore import (
    Qt, QSize, QTimer, QPropertyAnimation, QEasingCurve, QPoint
)
from PyQt6.QtGui import QColor, QFontDatabase, QFont

import qtawesome as qta
from config import BASE_DIR

# ایمپورت ویجت‌ها
from .dashboard_widget import DashboardWidget
from .categories_widget import CategoriesWidget
from .products_widget import ProductsWidget
from .orders_widget import OrdersWidget
from .settings_widget import SettingsWidget
from .users_widget import UsersWidget

# --- تنظیمات High DPI (باید قبل از ایجاد QApplication باشد، اما اینجا برای اطمینان می‌گذاریم) ---
if hasattr(Qt.ApplicationAttribute, 'AA_EnableHighDpiScaling'):
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
if hasattr(Qt.ApplicationAttribute, 'AA_UseHighDpiPixmaps'):
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

class MainWindow(QMainWindow):
    PAGE_MAP = {
        0: ("داشبورد", "fa5s.chart-pie"),
        1: ("محصولات", "fa5s.box-open"),
        2: ("دسته‌بندی‌ها", "fa5s.layer-group"),
        3: ("سفارشات", "fa5s.clipboard-list"),
        4: ("کاربران", "fa5s.users"),
        5: ("تنظیمات", "fa5s.cog"),
    }

    def __init__(self, bot_application: Optional[object] = None):
        super().__init__()
        self.bot_application = bot_application
        self.base_path = Path(BASE_DIR) / "admin_panel"
        
        # 1. تنظیمات پنجره
        self.setWindowTitle("مدیریت فروشگاه تلگرام | Deep Night Panel")
        self.resize(1300, 850)
        self.setMinimumSize(1100, 700)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setWindowIcon(qta.icon("fa5s.store", color="#7f5af0")) # رنگ بنفش نئونی

        # 2. لود فونت (اختیاری)
        self._load_font()

        # 3. متغیرهای وضعیت
        self.is_sidebar_collapsed = False
        
        # 4. راه‌اندازی رابط کاربری
        self.setup_ui()
        
        # 5. اعمال تم (فقط دارک)
        self.load_stylesheet()
        
        # 6. تایمر وضعیت
        self.check_connection_timer = QTimer(self)
        self.check_connection_timer.timeout.connect(self._safe_check_connection)
        self.check_connection_timer.start(10000)

    def _load_font(self):
        """تلاش برای لود فونت وزیرمتن از پوشه فونت‌ها"""
        # اگر فایل فونت را دارید در پوشه fonts قرار دهید
        font_path = self.base_path / "fonts" / "Vazirmatn.ttf" 
        if font_path.exists():
            QFontDatabase.addApplicationFont(str(font_path))
        
        # تنظیم فونت کلی برنامه
        font = QFont("Vazirmatn", 10)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        QApplication.setFont(font)

    def setup_ui(self):
        central_widget = QWidget()
        central_widget.setObjectName("centralwidget") # پس‌زمینه اصلی تیره (#16161a)
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15) # حاشیه دور کل برنامه
        main_layout.setSpacing(20) # فاصله بین سایدبار و محتوا

        # --- سایدبار ---
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar") # استایل در CSS
        self.sidebar.setFixedWidth(260)
        self.sidebar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        
        # سایه نرم بنفش/مشکی برای سایدبار
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 100))
        shadow.setOffset(0, 5)
        self.sidebar.setGraphicsEffect(shadow)
        
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(15, 25, 15, 20)
        sidebar_layout.setSpacing(8)

        # هدر سایدبار
        header_box = QHBoxLayout()
        header_box.setContentsMargins(0, 0, 0, 15)
        
        self.menu_btn = QPushButton()
        self.menu_btn.setIcon(qta.icon("fa5s.bars", color="#94a1b2"))
        self.menu_btn.setFixedSize(35, 35)
        self.menu_btn.setObjectName("menu_btn")
        self.menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.menu_btn.clicked.connect(self.toggle_sidebar)
        
        self.app_title = QLabel("پنل ادمین")
        self.app_title.setObjectName("app_title") # رنگ سفید و بولد
        
        header_box.addWidget(self.menu_btn)
        header_box.addWidget(self.app_title)
        header_box.addStretch()
        
        sidebar_layout.addLayout(header_box)
        
        # خط جداکننده (اختیاری، با CSS هندل می‌شود)
        
        # دکمه‌های منو
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons = []

        for index, (text_str, icon_name) in self.PAGE_MAP.items():
            btn = QPushButton(f"  {text_str}")
            # آیکون‌ها در حالت عادی خاکستری روشن
            btn.setIcon(qta.icon(icon_name, color="#94a1b2")) 
            btn.setIconSize(QSize(22, 22))
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(50)
            btn.setProperty("original_text", f"  {text_str}")
            
            self.nav_group.addButton(btn, index)
            self.nav_buttons.append(btn)
            sidebar_layout.addWidget(btn)

        sidebar_layout.addStretch()

        # وضعیت فوتر
        self.status_container = QFrame()
        self.status_container.setObjectName("status_container")
        status_layout = QVBoxLayout(self.status_container)
        status_layout.setContentsMargins(10, 10, 10, 10)
        
        self.status_label = QLabel("درحال راه‌اندازی...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setObjectName("status_label")
        
        status_layout.addWidget(self.status_label)
        sidebar_layout.addWidget(self.status_container)

        # --- محتوا ---
        self.content_area = QStackedWidget()
        self.content_area.setObjectName("content_area")
        
        # صفحات
        self.pages = [
            DashboardWidget(),
            ProductsWidget(bot_app=self.bot_application),
            CategoriesWidget(),
            OrdersWidget(bot_app=self.bot_application),
            UsersWidget(),
            SettingsWidget(),
        ]
        
        for page in self.pages:
            self.content_area.addWidget(page)

        # اتصال
        self.nav_group.idClicked.connect(self.switch_page)

        # انتخاب پیش‌فرض
        self.nav_buttons[0].setChecked(True)
        self.content_area.setCurrentIndex(0)
        self._update_btn_icons(self.nav_buttons[0]) # آپدیت رنگ آیکون فعال

        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(self.content_area)

    def switch_page(self, page_id):
        current_page = self.content_area.widget(page_id)
        if self.content_area.currentWidget() == current_page:
            return

        # تغییر رنگ آیکون دکمه فعال
        for btn in self.nav_buttons:
            if self.nav_group.id(btn) == page_id:
                # آیکون فعال: سفید
                icon_name = self.PAGE_MAP[page_id][1]
                btn.setIcon(qta.icon(icon_name, color="#ffffff"))
            else:
                # آیکون غیرفعال: خاکستری
                idx = self.nav_group.id(btn)
                icon_name = self.PAGE_MAP[idx][1]
                btn.setIcon(qta.icon(icon_name, color="#94a1b2"))

        self.content_area.setCurrentIndex(page_id)
        
        # انیمیشن ورود
        anim = QPropertyAnimation(current_page, b"windowOpacity")
        anim.setDuration(300)
        anim.setStartValue(0)
        anim.setEndValue(1)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()

        if hasattr(current_page, "refresh_data"):
            result = current_page.refresh_data()
            if asyncio.iscoroutine(result):
                asyncio.create_task(result)

    def _update_btn_icons(self, active_btn):
        """تابع کمکی برای ست کردن رنگ آیکون اولیه"""
        for btn in self.nav_buttons:
            idx = self.nav_group.id(btn)
            icon_name = self.PAGE_MAP[idx][1]
            if btn == active_btn:
                btn.setIcon(qta.icon(icon_name, color="#ffffff"))
            else:
                btn.setIcon(qta.icon(icon_name, color="#94a1b2"))

    def toggle_sidebar(self):
        width = self.sidebar.width()
        start_width = 260
        collapsed_width = 70 # کمی باریک‌تر برای زیبایی
        
        if width > 100:
            end_width = collapsed_width
            self.app_title.hide()
            self.status_container.hide()
            self.is_sidebar_collapsed = True
            for btn in self.nav_buttons:
                btn.setText("")
                btn.setToolTip(btn.property("original_text").strip())
        else:
            end_width = start_width
            self.is_sidebar_collapsed = False
            for btn in self.nav_buttons:
                btn.setText(btn.property("original_text"))
                btn.setToolTip("")

        self.anim = QPropertyAnimation(self.sidebar, b"minimumWidth")
        self.anim.setDuration(400) # کمی کندتر و نرم‌تر
        self.anim.setStartValue(width)
        self.anim.setEndValue(end_width)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutQuart)
        self.anim.start()
        
        self.sidebar.setMaximumWidth(end_width)

        if not self.is_sidebar_collapsed:
            QTimer.singleShot(350, self.app_title.show)
            QTimer.singleShot(350, self.status_container.show)

    def load_stylesheet(self):
        """بارگذاری مستقیم تم دارک"""
        # فایل دارک تم باید در مسیر مشخص شده باشد
        theme_path = self.base_path / "themes" / "dark_theme.qss"
        if theme_path.exists():
            with open(theme_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        else:
            print("Dark theme file not found!")

    def _safe_check_connection(self):
        if self.bot_application:
             self.status_label.setText("🟢 متصل")
             self.status_label.setStyleSheet("color: #2cb67d; font-weight: bold;")
        else:
             self.status_label.setText("🔴 قطع")
             self.status_label.setStyleSheet("color: #ef476f; font-weight: bold;")