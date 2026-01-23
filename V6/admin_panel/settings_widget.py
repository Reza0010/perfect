import asyncio
import shutil
import logging
import re
import os
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QPushButton, QMessageBox, QCheckBox,
    QFileDialog, QFrame, QScrollArea, QTimeEdit, QListWidget, QListWidgetItem,
    QStackedWidget, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QComboBox, QProgressBar
)
from PyQt6.QtGui import QColor, QPainter, QFont, QPixmap, QDoubleValidator
from PyQt6.QtCore import Qt, QTimer, QTime, QPropertyAnimation, QEasingCurve, pyqtProperty, pyqtSignal
from qasync import asyncSlot
import qtawesome as qta
from telegram import BotCommand

# Project Imports
from db.database import get_db
from db import crud
from config import BASE_DIR, ADMIN_USER_IDS

logger = logging.getLogger(__name__)

# ==============================================================================
# Helper Widgets
# ==============================================================================
class FormattedInput(QLineEdit):
    """ورودی عدد با جداکننده هزارگان"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.textChanged.connect(self.format_text)
        self.setStyleSheet("""
            QLineEdit { background: #16161a; border: 1px solid #3a3a4e; border-radius: 8px; padding: 10px; color: #2cb67d; font-weight: bold; font-size: 14px; }
            QLineEdit:focus { border: 1px solid #2cb67d; }
        """)
        
    def format_text(self, text):
        if not text: return
        clean = re.sub(r'[^\d]', '', text)
        if not clean: return
        try:
            formatted = "{:,}".format(int(clean))
            if text != formatted:
                self.blockSignals(True)
                self.setText(formatted)
                self.setCursorPosition(len(formatted))
                self.blockSignals(False)
        except: pass

class ToggleSwitch(QCheckBox):
    """دکمه تغییر وضعیت مدرن"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(50, 26)
        self._circle_position = 3
        self.animation = QPropertyAnimation(self, b"circle_position", self)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animation.setDuration(300)
        self.stateChanged.connect(self.start_transition)

    @pyqtProperty(int)
    def circle_position(self): return self._circle_position
    @circle_position.setter
    def circle_position(self, pos): self._circle_position = pos; self.update()

    def start_transition(self, state):
        self.animation.stop()
        self.animation.setEndValue(self.width() - 23 if state else 3)
        self.animation.start()

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#2cb67d") if self.isChecked() else QColor("#4a4a62"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, self.width(), self.height(), 13, 13)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(self._circle_position, 3, 20, 20)
        p.end()

class SettingCard(QFrame):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame { background-color: #242629; border-radius: 12px; border: 1px solid #2b2c37; }
            QLabel { color: #e4e5f1; font-size: 13px; font-weight: 500; border: none; background: transparent; }
            QLineEdit, QTextEdit, QComboBox, QTimeEdit {
                background-color: #16161a; color: white; border: 1px solid #3a3a4e; border-radius: 8px; padding: 8px;
            }
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus { border: 1px solid #7f5af0; }
        """)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)
        
        lbl = QLabel(title)
        lbl.setStyleSheet("color: #7f5af0; font-weight: bold; font-size: 15px;")
        self.layout.addWidget(lbl)
        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine); line.setStyleSheet("background: #2b2c37; max-height: 1px;")
        self.layout.addWidget(line)

    def add_widget(self, w): self.layout.addWidget(w)
    def add_layout(self, l): self.layout.addLayout(l)

# ==============================================================================
# Main Settings Widget
# ==============================================================================
class SettingsWidget(QWidget):
    WELCOME_TEMPLATES = {
        "سفارشی (خالی)": "",
        "پیش‌فرض (ساده)": "سلام {user_name} عزیز 👋\nبه فروشگاه {shop_name} خوش آمدید.\nبرای شروع خرید از دکمه‌های زیر استفاده کنید.",
        "رسمی": "با سلام و احترام،\nکاربر گرامی {user_name}، ورود شما به سامانه فروش {shop_name} را گرامی می‌داریم.",
        "فروش ویژه": "🔥 سلام {user_name}!\nبه بزرگترین حراجی {shop_name} خوش اومدی!\n🎁 همین الان از تخفیف‌ها لذت ببر."
    }

    DEFAULT_SETTINGS = {
        "shop_name": "فروشگاه من",
        "shop_is_open": "true",
        "welcome_message": "",
        "welcome_image": "",
        "channel_link": "",
        "support_id": "",
        "contact_phone": "",
        "shipping_cost": "0",
        "free_shipping_limit": "0",
        "card_number": "",
        "card_owner": "",
        "auto_backup_enabled": "false",
        "auto_backup_time": "00:00",
        "shop_address": ""
    }

    def __init__(self):
        super().__init__()
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setup_ui()
        
        # تغییر مهم: حذف تسک از اینجا و انتقال به showEvent با تاخیر
        self._data_loaded = False
        self._backup_task_started = False

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0); main_layout.setSpacing(0)

        # 1. Sidebar
        self.nav_list = QListWidget()
        self.nav_list.setFixedWidth(240)
        self.nav_list.setStyleSheet("""
            QListWidget { background: #16161a; border-left: 1px solid #2b2c37; padding-top: 20px; outline: none; }
            QListWidget::item { height: 50px; color: #94a1b2; padding-right: 15px; border-right: 4px solid transparent; font-size: 14px; }
            QListWidget::item:selected { color: #fffffe; background: #21212e; border-right: 4px solid #7f5af0; font-weight: bold; }
            QListWidget::item:hover { background: #1c1c24; }
        """)
        
        for t, i in [(" تنظیمات عمومی", "fa5s.store"), (" مالی و ارسال", "fa5s.credit-card"), (" ابزارها و بک‌آپ", "fa5s.tools"), (" گزارشات سیستم", "fa5s.file-alt")]:
            item = QListWidgetItem(t); item.setIcon(qta.icon(i, color="#7f5af0")); self.nav_list.addItem(item)

        self.nav_list.currentRowChanged.connect(self.change_page)
        main_layout.addWidget(self.nav_list)

        # 2. Content Stack
        self.pages_stack = QStackedWidget()
        self.pages_stack.addWidget(self._ui_general_page())
        self.pages_stack.addWidget(self._ui_payment_page())
        self.pages_stack.addWidget(self._ui_tools_page())
        self.pages_stack.addWidget(self._ui_logs_page())
        main_layout.addWidget(self.pages_stack)
        self.nav_list.setCurrentRow(0)
        
    def showEvent(self, event):
        super().showEvent(event)
        if not self._data_loaded:
            QTimer.singleShot(200, self.refresh_data)
            self._data_loaded = True
            
        # شروع لوپ بک‌آپ فقط یک بار و با تاخیر زیاد
        if not self._backup_task_started:
            QTimer.singleShot(5000, lambda: asyncio.create_task(self._scheduled_backup_loop()))
            self._backup_task_started = True 

    def change_page(self, index):
        self.pages_stack.setCurrentIndex(index)
        anim = QPropertyAnimation(self.pages_stack, b"windowOpacity")
        anim.setDuration(300); anim.setStartValue(0); anim.setEndValue(1); anim.start()

    # --- Pages ---
    def _ui_general_page(self):
        page = QWidget()
        layout = QVBoxLayout(page); layout.setContentsMargins(20, 20, 20, 20)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setStyleSheet("background: transparent; border: none;")
        container = QWidget(); v_box = QVBoxLayout(container); v_box.setSpacing(20)

        # Card 1: Identity
        card1 = SettingCard("هویت فروشگاه")
        row1 = QHBoxLayout()
        self.shop_name = QLineEdit(); self.shop_name.setPlaceholderText("مثلاً: موبایل سنتر")
        self.toggle_status = ToggleSwitch()
        row1.addWidget(QLabel("نام فروشگاه:")); row1.addWidget(self.shop_name); row1.addStretch(); row1.addWidget(QLabel("وضعیت (باز/بسته):")); row1.addWidget(self.toggle_status)
        self.shop_address = QTextEdit(); self.shop_address.setPlaceholderText("آدرس فیزیکی..."); self.shop_address.setMaximumHeight(60)
        card1.add_layout(row1); card1.add_widget(QLabel("آدرس فروشگاه:")); card1.add_widget(self.shop_address)
        v_box.addWidget(card1)

        # Card 2: Contact
        card2 = SettingCard("ارتباطات")
        self.channel_link = QLineEdit(); self.channel_link.setPlaceholderText("https://t.me/...")
        row2 = QHBoxLayout()
        self.support_id = QLineEdit(); self.support_id.setPlaceholderText("@Admin")
        self.contact_phone = QLineEdit(); self.contact_phone.setPlaceholderText("0912...")
        row2.addWidget(QLabel("آیدی پشتیبان:")); row2.addWidget(self.support_id); row2.addWidget(QLabel("تلفن:")); row2.addWidget(self.contact_phone)
        card2.add_widget(QLabel("لینک کانال:")); card2.add_widget(self.channel_link); card2.add_layout(row2)
        v_box.addWidget(card2)

        # Card 3: Welcome Message
        card3 = SettingCard("شخصی‌سازی ربات (/start)")
        h_prev = QHBoxLayout()
        v_edit = QVBoxLayout()
        self.template_combo = QComboBox(); self.template_combo.addItems(self.WELCOME_TEMPLATES.keys()); self.template_combo.currentIndexChanged.connect(self.apply_template)
        self.welcome_msg = QTextEdit(); self.welcome_msg.setPlaceholderText("متن خوش‌آمدگویی..."); self.welcome_msg.textChanged.connect(self.update_preview)
        v_edit.addWidget(QLabel("قالب آماده:")); v_edit.addWidget(self.template_combo); v_edit.addWidget(QLabel("متن پیام:")); v_edit.addWidget(self.welcome_msg)
        
        # Preview Box
        prev_frame = QFrame(); prev_frame.setFixedWidth(280); prev_frame.setStyleSheet("background: #182533; border-radius: 12px; border: 1px solid black;")
        p_lay = QVBoxLayout(prev_frame); p_lay.setContentsMargins(10,10,10,10)
        self.preview_img = QLabel("No Image"); self.preview_img.setAlignment(Qt.AlignmentFlag.AlignCenter); self.preview_img.setFixedHeight(120); self.preview_img.setStyleSheet("background: #101010; border-radius: 8px; color: #555;")
        self.preview_lbl = QLabel(); self.preview_lbl.setWordWrap(True); self.preview_lbl.setStyleSheet("color: white; font-size: 13px;")
        msg_bubble = QFrame(); msg_bubble.setStyleSheet("background: #2b5278; border-radius: 8px; padding: 8px;")
        m_lay = QVBoxLayout(msg_bubble); m_lay.addWidget(self.preview_lbl)
        p_lay.addWidget(self.preview_img); p_lay.addWidget(msg_bubble); p_lay.addStretch()
        h_prev.addLayout(v_edit); h_prev.addWidget(prev_frame)
        card3.add_layout(h_prev)

        # Banner
        h_bnr = QHBoxLayout()
        self.welcome_img_path = QLineEdit(); self.welcome_img_path.setReadOnly(True)
        btn_img = QPushButton("انتخاب بنر"); btn_img.clicked.connect(self.on_select_image); btn_img.setStyleSheet("background: #3da9fc; color: white; border-radius: 6px; padding: 6px;")
        btn_del = QPushButton(); btn_del.setIcon(qta.icon('fa5s.trash', color='#ef4565')); btn_del.clicked.connect(self.clear_banner_image); btn_del.setStyleSheet("background: transparent; border: 1px solid #ef4565; border-radius: 6px;")
        h_bnr.addWidget(self.welcome_img_path); h_bnr.addWidget(btn_img); h_bnr.addWidget(btn_del)
        card3.add_layout(h_bnr)
        
        btn_cmd = QPushButton("  بروزرسانی منوی ربات"); btn_cmd.setIcon(qta.icon('fa5s.robot', color='#3da9fc')); btn_cmd.clicked.connect(self.update_bot_commands)
        btn_cmd.setStyleSheet("background: #21212e; border: 1px dashed #3da9fc; color: #3da9fc; border-radius: 8px; padding: 8px;")
        card3.add_widget(btn_cmd)
        v_box.addWidget(card3)

        self.btn_save_gen = QPushButton("ذخیره تمام تغییرات"); self.btn_save_gen.clicked.connect(self.save_settings)
        self.btn_save_gen.setStyleSheet("background: #7f5af0; color: white; padding: 12px; border-radius: 8px; font-weight: bold; font-size: 14px;")
        v_box.addWidget(self.btn_save_gen); v_box.addStretch()
        scroll.setWidget(container); layout.addWidget(scroll)
        return page

    def _ui_payment_page(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(30, 30, 30, 30)
        
        card1 = SettingCard("درگاه کارت به کارت")
        self.card_num = QLineEdit(); self.card_num.setPlaceholderText("XXXX-XXXX-XXXX-XXXX"); self.card_num.textChanged.connect(self.format_card_number)
        self.card_owner = QLineEdit()
        card1.add_widget(QLabel("شماره کارت:")); card1.add_widget(self.card_num)
        card1.add_widget(QLabel("صاحب حساب:")); card1.add_widget(self.card_owner)
        layout.addWidget(card1)

        card2 = SettingCard("تنظیمات ارسال")
        self.shipping_cost = FormattedInput()
        self.free_limit = FormattedInput()
        card2.add_widget(QLabel("هزینه ارسال ثابت (تومان):")); card2.add_widget(self.shipping_cost)
        card2.add_widget(QLabel("سقف ارسال رایگان (تومان):")); card2.add_widget(self.free_limit)
        layout.addWidget(card2)
        
        btn = QPushButton("ذخیره تنظیمات"); btn.clicked.connect(self.save_settings)
        btn.setStyleSheet("background: #2cb67d; color: white; padding: 12px; border-radius: 8px; font-weight: bold;")
        layout.addWidget(btn); layout.addStretch()
        return page

    def _ui_tools_page(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(30, 30, 30, 30)
        
        card_bk = SettingCard("مدیریت بک‌آپ (Backups)")
        self.bk_table = QTableWidget(0, 3); self.bk_table.setHorizontalHeaderLabels(["نام فایل", "تاریخ", "حجم"])
        self.bk_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.bk_table.setStyleSheet("background: #16161a; border-radius: 8px;")
        
        h_bk = QHBoxLayout()
        b1 = QPushButton("ایجاد بک‌آپ"); b1.clicked.connect(self.create_manual_backup); b1.setStyleSheet("background: #3da9fc; color: white; border-radius: 6px; padding: 8px;")
        b2 = QPushButton("بازگردانی"); b2.clicked.connect(self.restore_backup); b2.setStyleSheet("background: #ef4565; color: white; border-radius: 6px; padding: 8px;")
        b3 = QPushButton(); b3.setIcon(qta.icon('fa5s.sync', color='white')); b3.clicked.connect(self.load_backups_list); b3.setStyleSheet("background: #3a3a4e; border-radius: 6px; padding: 8px;")
        h_bk.addWidget(b1); h_bk.addWidget(b2); h_bk.addWidget(b3)
        
        h_auto = QHBoxLayout()
        self.auto_bk_toggle = ToggleSwitch(); self.auto_bk_time = QTimeEdit()
        h_auto.addWidget(QLabel("بک‌آپ خودکار روزانه:")); h_auto.addWidget(self.auto_bk_toggle); h_auto.addSpacing(20); h_auto.addWidget(QLabel("زمان:")); h_auto.addWidget(self.auto_bk_time); h_auto.addStretch()
        
        card_bk.add_widget(self.bk_table); card_bk.add_layout(h_bk); card_bk.add_layout(h_auto)
        layout.addWidget(card_bk)

        card_bc = SettingCard("ارسال پیام همگانی (Broadcast)")
        self.bc_text = QTextEdit(); self.bc_text.setPlaceholderText("پیام شما..."); self.bc_text.setMaximumHeight(80)
        self.bc_progress = QProgressBar(); self.bc_progress.hide()
        btn_bc = QPushButton("ارسال به همه کاربران"); btn_bc.setStyleSheet("background: #ef4565; color: white; padding: 10px; border-radius: 8px; font-weight: bold;")
        btn_bc.clicked.connect(self.on_start_broadcast)
        card_bc.add_widget(self.bc_text); card_bc.add_widget(self.bc_progress); card_bc.add_widget(btn_bc)
        layout.addWidget(card_bc); layout.addStretch()
        QTimer.singleShot(500, self.load_backups_list)
        return page

    def _ui_logs_page(self):
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(30, 30, 30, 30)
        card = SettingCard("لاگ‌های سیستم")
        
        self.log_viewer = QTextEdit(); self.log_viewer.setReadOnly(True)
        self.log_viewer.setStyleSheet("background: #0f1015; color: #ccc; font-family: Consolas; font-size: 12px; border-radius: 8px; padding: 10px;")
        
        h_btn = QHBoxLayout()
        self.filter_combo = QComboBox(); self.filter_combo.addItems(["همه", "ERROR", "WARNING", "INFO"])
        self.filter_combo.currentTextChanged.connect(self.read_app_logs)
        btn_clr = QPushButton("پاکسازی"); btn_clr.clicked.connect(self.clear_log_file); btn_clr.setStyleSheet("background: #e74c3c; color: white; padding: 6px; border-radius: 6px;")
        btn_ref = QPushButton("بروزرسانی"); btn_ref.clicked.connect(self.read_app_logs); btn_ref.setStyleSheet("background: #3498db; color: white; padding: 6px; border-radius: 6px;")
        
        h_btn.addWidget(QLabel("فیلتر:")); h_btn.addWidget(self.filter_combo); h_btn.addStretch(); h_btn.addWidget(btn_clr); h_btn.addWidget(btn_ref)
        card.add_widget(self.log_viewer); card.add_layout(h_btn)
        layout.addWidget(card)
        return page

    # --- Logic ---
    def update_preview(self):
        text = self.welcome_msg.toPlainText()
        text = text.replace("{shop_name}", self.shop_name.text() or "فروشگاه").replace("{user_name}", "کاربر")
        self.preview_lbl.setText(text)

    def format_card_number(self, text):
        digits = re.sub(r'\D', '', text)[:16]
        formatted = '-'.join([digits[i:i+4] for i in range(0, len(digits), 4)])
        if self.card_num.text() != formatted:
            self.card_num.blockSignals(True); self.card_num.setText(formatted); self.card_num.setCursorPosition(len(formatted)); self.card_num.blockSignals(False)

    def apply_template(self):
        t = self.template_combo.currentText()
        if t in self.WELCOME_TEMPLATES: self.welcome_msg.setPlainText(self.WELCOME_TEMPLATES[t])

    def on_select_image(self):
        f, _ = QFileDialog.getOpenFileName(self, "تصویر", "", "Images (*.jpg *.png *.jpeg)")
        if f: self.welcome_img_path.setText(f); self._update_preview_image(f)

    def clear_banner_image(self):
        self.welcome_img_path.clear(); self._update_preview_image(None)

    def _update_preview_image(self, path):
        if path and os.path.exists(path):
            self.preview_img.setPixmap(QPixmap(path).scaled(280, 150, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else: self.preview_img.clear(); self.preview_img.setText("بدون عکس")

    def read_app_logs(self):
        path = BASE_DIR / "logs" / "app.log"
        if not path.exists(): return self.log_viewer.setPlainText("لاگ یافت نشد.")
        try:
            with open(path, "r", encoding="utf-8") as f: lines = f.readlines()[-150:]
            html = ""
            filter_key = self.filter_combo.currentText()
            for line in lines:
                if filter_key != "همه" and filter_key not in line: continue
                col = "#ef4565" if "ERROR" in line else ("#f1c40f" if "WARNING" in line else ("#2cb67d" if "INFO" in line else "#94a1b2"))
                html += f"<div style='color:{col}'>{line.strip()}</div>"
            self.log_viewer.setHtml(html)
            self.log_viewer.verticalScrollBar().setValue(self.log_viewer.verticalScrollBar().maximum())
        except: pass

    def clear_log_file(self):
        try: open(BASE_DIR / "logs" / "app.log", 'w').close(); self.read_app_logs()
        except: pass

    @asyncSlot()
    async def refresh_data(self):
        loop = asyncio.get_running_loop()
        try:
            data = await loop.run_in_executor(None, lambda: self._fetch_all_settings())
            
            self.shop_name.setText(data["shop_name"])
            self.toggle_status.setChecked(data["shop_is_open"] == "true")
            self.shop_address.setPlainText(data["shop_address"])
            self.welcome_msg.setPlainText(data["welcome_message"])
            self.welcome_img_path.setText(data["welcome_image"])
            self.channel_link.setText(data["channel_link"])
            self.support_id.setText(data["support_id"])
            self.contact_phone.setText(data["contact_phone"])
            self.card_num.setText(data["card_number"])
            self.card_owner.setText(data["card_owner"])
            self.shipping_cost.setText(data["shipping_cost"]) # FormattedInput خودش کاما می‌گذارد
            self.free_limit.setText(data["free_shipping_limit"])
            
            self.auto_bk_toggle.setChecked(data["auto_backup_enabled"] == "true")
            try: self.auto_bk_time.setTime(QTime.fromString(data["auto_backup_time"], "HH:mm"))
            except: pass
            
            img = data["welcome_image"]
            if img and not os.path.isabs(img): img = str(BASE_DIR / img)
            self._update_preview_image(img)
            self.read_app_logs()
        except Exception as e: logger.error(e)

    def _fetch_all_settings(self):
        with next(get_db()) as db:
            return {k: crud.get_setting(db, k, v) for k, v in self.DEFAULT_SETTINGS.items()}

    @asyncSlot()
    async def save_settings(self):
        img = self.welcome_img_path.text()
        if img and not img.startswith("media/") and os.path.exists(img):
            dest = BASE_DIR / "media" / f"banner_start{Path(img).suffix}"
            shutil.copy2(img, dest)
            img = f"media/{dest.name}"

        data = {
            "shop_name": self.shop_name.text(),
            "shop_is_open": "true" if self.toggle_status.isChecked() else "false",
            "shop_address": self.shop_address.toPlainText(),
            "welcome_message": self.welcome_msg.toPlainText(),
            "welcome_image": img,
            "channel_link": self.channel_link.text(),
            "support_id": self.support_id.text(),
            "contact_phone": self.contact_phone.text(),
            "card_number": self.card_num.text(),
            "card_owner": self.card_owner.text(),
            "shipping_cost": re.sub(r'[^\d]', '', self.shipping_cost.text()),
            "free_shipping_limit": re.sub(r'[^\d]', '', self.free_limit.text()),
            "auto_backup_enabled": "true" if self.auto_bk_toggle.isChecked() else "false",
            "auto_backup_time": self.auto_bk_time.time().toString("HH:mm"),
        }
        
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: self._save_db(data))
        
        self.btn_save_gen.setText("✅ ذخیره شد"); self.btn_save_gen.setStyleSheet("background: #2cb67d; color: white; padding: 12px; border-radius: 8px; border:none;")
        QTimer.singleShot(2000, lambda: self.btn_save_gen.setText("ذخیره تمام تغییرات"))
        QTimer.singleShot(2000, lambda: self.btn_save_gen.setStyleSheet("background: #7f5af0; color: white; padding: 12px; border-radius: 8px; border:none;"))
        if hasattr(self.window(), 'show_toast'): self.window().show_toast("تنظیمات ذخیره شد.")

    def _save_db(self, data):
        with next(get_db()) as db:
            for k, v in data.items(): crud.set_setting(db, k, v)

    @asyncSlot()
    async def update_bot_commands(self):
        mw = self.window()
        if not hasattr(mw, 'bot_application') or not mw.bot_application: return QMessageBox.warning(self, "خطا", "ربات متصل نیست.")
        try:
            await mw.bot_application.bot.set_my_commands([
                BotCommand("start", "🏠 خانه"), BotCommand("cart", "🛒 سبد خرید"),
                BotCommand("search", "🔍 جستجو"), BotCommand("support", "📞 پشتیبانی")
            ])
            if hasattr(mw, 'show_toast'): mw.show_toast("منوی ربات بروزرسانی شد.")
        except Exception as e: QMessageBox.warning(self, "خطا", str(e))

    # --- Backup & Broadcast (Simplified) ---
    def create_manual_backup(self):
        try:
            n = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            dest = BASE_DIR / "db" / "backups"
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(BASE_DIR / "db" / "shop_bot.db", dest / n)
            self.load_backups_list()
            if hasattr(self.window(), 'show_toast'): self.window().show_toast("بک‌آپ ایجاد شد.")
        except Exception as e: QMessageBox.critical(self, "خطا", str(e))

    def load_backups_list(self):
        self.bk_table.setRowCount(0)
        d = BASE_DIR / "db" / "backups"
        if not d.exists(): return
        for i, f in enumerate(sorted(d.glob("*.db"), key=os.path.getmtime, reverse=True)):
            self.bk_table.insertRow(i)
            self.bk_table.setItem(i, 0, QTableWidgetItem(f.name))
            self.bk_table.setItem(i, 1, QTableWidgetItem(datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")))
            self.bk_table.setItem(i, 2, QTableWidgetItem(f"{f.stat().st_size/1024:.1f} KB"))

    def restore_backup(self):
        r = self.bk_table.currentRow()
        if r < 0: return
        f = self.bk_table.item(r, 0).text()
        if QMessageBox.question(self, "هشدار", f"بازگردانی {f}؟ برنامه بسته می‌شود.") == QMessageBox.StandardButton.Yes:
            try:
                shutil.copy2(BASE_DIR / "db" / "backups" / f, BASE_DIR / "db" / "shop_bot.db")
                os._exit(0)
            except Exception as e: QMessageBox.critical(self, "خطا", str(e))

    @asyncSlot()
    async def on_start_broadcast(self):
        txt = self.bc_text.toPlainText().strip()
        if not txt: return
        mw = self.window()
        if not hasattr(mw, 'bot_application'): return
        
        self.bc_progress.show(); self.bc_progress.setValue(0)
        loop = asyncio.get_running_loop()
        users = await loop.run_in_executor(None, lambda: crud.get_all_users(next(get_db())))
        self.bc_progress.setMaximum(len(users))
        
        success = 0
        for i, u in enumerate(users):
            try:
                await mw.bot_application.bot.send_message(chat_id=u.user_id, text=txt, parse_mode='HTML')
                success += 1
            except: pass
            self.bc_progress.setValue(i+1)
            if i % 20 == 0: await asyncio.sleep(1)
        
        self.bc_progress.hide()
        QMessageBox.information(self, "پایان", f"ارسال شد به {success} نفر.")

    async def _scheduled_backup_loop(self):
        """لوپ بررسی زمان بک‌آپ خودکار"""
        while True:
            try:
                # اول ۶۰ ثانیه صبر کن، بعد چک کن
                await asyncio.sleep(60)
                
                # بررسی اینکه آیا برنامه هنوز باز است؟
                if not self.isVisible(): continue

                loop = asyncio.get_running_loop()
                res = await loop.run_in_executor(None, lambda: self._check_auto_backup())
                if res: await self.perform_auto_backup()
            except asyncio.CancelledError:
                break # اگر برنامه بسته شد، لوپ هم قطع شود
            except Exception: pass

    def _check_auto_backup(self):
        with next(get_db()) as db:
            return crud.get_setting(db, "auto_backup_enabled") == "true" and \
                   datetime.now().strftime("%H:%M") == crud.get_setting(db, "auto_backup_time")

    async def perform_auto_backup(self):
        mw = self.window()
        if not hasattr(mw, 'bot_application') or not ADMIN_USER_IDS: return
        try:
            await mw.bot_application.bot.send_document(
                chat_id=ADMIN_USER_IDS[0],
                document=open(BASE_DIR / "db" / "shop_bot.db", 'rb'),
                caption=f"📦 Backup {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            )
        except: pass