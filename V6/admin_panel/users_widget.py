import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QFrame, QGridLayout, QLineEdit, QMessageBox, 
    QGraphicsDropShadowEffect, QTextEdit, QDialog, QLayout, QStyle, QSizePolicy
)
from PyQt6.QtGui import QColor, QFont, QCursor, QPainter
from PyQt6.QtCore import Qt, QSize, QTimer, QRect, QPoint
from qasync import asyncSlot
import qtawesome as qta

from db.database import SessionLocal
from db import crud, models

# ==============================================================================
# Helper: Flow Layout (چیدمان شناور برای ریسپانسیو بودن)
# ==============================================================================
class FlowLayout(QLayout):
    """لی‌اوت سفارشی که ویجت‌ها را مثل کلمات در یک پاراگراف می‌چیند"""
    def __init__(self, parent=None, margin=0, spacing=-1):
        super(FlowLayout, self).__init__(parent)
        if parent is not None: self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self.itemList = []

    def __del__(self):
        item = self.takeAt(0)
        while item: item = self.takeAt(0)

    def addItem(self, item): self.itemList.append(item)
    def count(self): return len(self.itemList)
    def itemAt(self, index): return self.itemList[index] if 0 <= index < len(self.itemList) else None
    
    def takeAt(self, index):
        if 0 <= index < len(self.itemList): return self.itemList.pop(index)
        return None

    def expandingDirections(self): return Qt.Orientation(0)
    def hasHeightForWidth(self): return True
    def heightForWidth(self, width): return self.doLayout(QRect(0, 0, width, 0), True)
    def setGeometry(self, rect): super(FlowLayout, self).setGeometry(rect); self.doLayout(rect, False)
    def sizeHint(self): return self.minimumSize()
    def minimumSize(self):
        size = QSize()
        for item in self.itemList: size = size.expandedTo(item.minimumSize())
        size += QSize(2 * self.contentsMargins().top(), 2 * self.contentsMargins().top())
        return size

    def doLayout(self, rect, testOnly):
        x, y = rect.x(), rect.y()
        lineHeight = 0
        spacing = self.spacing()
        for item in self.itemList:
            wid = item.widget()
            spaceX = spacing + wid.style().layoutSpacing(QSizePolicy.ControlType.PushButton, QSizePolicy.ControlType.PushButton, Qt.Orientation.Horizontal)
            spaceY = spacing + wid.style().layoutSpacing(QSizePolicy.ControlType.PushButton, QSizePolicy.ControlType.PushButton, Qt.Orientation.Vertical)
            nextX = x + item.sizeHint().width() + spaceX
            if nextX - spaceX > rect.right() and lineHeight > 0:
                x = rect.x()
                y = y + lineHeight + spaceY
                nextX = x + item.sizeHint().width() + spaceX
                lineHeight = 0
            if not testOnly: item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())
        return y + lineHeight - rect.y()

# ==============================================================================
# کامپوننت ۱: کارت هوشمند کاربر
# ==============================================================================
class UserCard(QFrame):
    def __init__(self, user_data: Any, parent_widget):
        super().__init__()
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.user = user_data
        self.parent_widget = parent_widget
        
        self.setFixedSize(300, 210)
        self.setObjectName("user_card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # محاسبه سطح کاربر
        total_spent = getattr(user_data, 'total_spent', 0)
        order_count = getattr(user_data, 'order_count', 0)
        
        if total_spent > 10_000_000:
            self.badge_col = "#f1c40f"; self.badge_icon = "fa5s.crown"; self.badge_title = "VIP طلایی"
        elif total_spent > 3_000_000:
            self.badge_col = "#bdc3c7"; self.badge_icon = "fa5s.star"; self.badge_title = "مشتری نقره‌ای"
        elif order_count > 0:
            self.badge_col = "#2cb67d"; self.badge_icon = "fa5s.user"; self.badge_title = "مشتری فعال"
        else:
            self.badge_col = "#94a1b2"; self.badge_icon = "fa5s.user-tag"; self.badge_title = "کاربر جدید"

        border_col = "#ef4565" if getattr(user_data, 'is_banned', False) else "#2b2c37"
        bg_col = "#242629"

        self.setStyleSheet(f"""
            QFrame#user_card {{
                background-color: {bg_col};
                border-radius: 14px;
                border: 1px solid {border_col};
            }}
            QFrame#user_card:hover {{
                background-color: #2a2c30;
                border: 1px solid #7f5af0;
            }}
            QLabel {{ border: none; background: transparent; color: #fffffe; }}
        """)
        
        shadow = QGraphicsDropShadowEffect(); shadow.setBlurRadius(15); shadow.setColor(QColor(0,0,0,60)); shadow.setOffset(0,4)
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self); layout.setContentsMargins(15, 15, 15, 15); layout.setSpacing(10)

        # Header
        h_layout = QHBoxLayout()
        icon = QLabel(); icon.setFixedSize(40, 40); icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(f"background: {self.badge_col}20; border-radius: 20px;")
        icon.setPixmap(qta.icon(self.badge_icon, color=self.badge_col).pixmap(20,20))
        
        v_info = QVBoxLayout(); v_info.setSpacing(2)
        name = getattr(self.user, 'full_name', "بدون نام") or "کاربر ناشناس"
        lbl_name = QLabel(name); lbl_name.setStyleSheet("font-weight: bold; font-size: 14px;")
        lbl_id = QLabel(f"ID: {getattr(self.user, 'user_id', 0)}"); lbl_id.setStyleSheet("color: #888; font-size: 11px;")
        v_info.addWidget(lbl_name); v_info.addWidget(lbl_id)
        
        # بج وضعیت
        lbl_badge = QLabel(self.badge_title)
        lbl_badge.setStyleSheet(f"color: {self.badge_col}; font-size: 10px; border: 1px solid {self.badge_col}; border-radius: 4px; padding: 2px 5px;")
        
        h_layout.addWidget(icon); h_layout.addLayout(v_info); h_layout.addStretch(); h_layout.addWidget(lbl_badge, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(h_layout)

        # Stats
        stats = QHBoxLayout(); stats.setSpacing(10)
        stats.addWidget(self._stat_box(str(order_count), "سفارش"))
        stats.addWidget(self._stat_box(f"{int(total_spent):,}", "تومان خرید"))
        layout.addLayout(stats)

        # Actions
        actions = QHBoxLayout(); actions.setSpacing(8)
        
        has_note = bool(getattr(self.user, 'private_note', None))
        btn_note = self._btn("fa5s.sticky-note", "#f1c40f" if has_note else "#3a3a4e", "یادداشت"); btn_note.clicked.connect(self.open_note)
        btn_chat = self._btn("fa5s.paper-plane", "#3da9fc", "چت تلگرام"); btn_chat.clicked.connect(self.open_chat)
        
        is_banned = getattr(self.user, 'is_banned', False)
        btn_ban = self._btn("fa5s.unlock" if is_banned else "fa5s.ban", "#2cb67d" if is_banned else "#ef4565", "آزاد کردن" if is_banned else "مسدود کردن")
        btn_ban.clicked.connect(self.toggle_ban)
        
        actions.addStretch(); actions.addWidget(btn_note); actions.addWidget(btn_chat); actions.addWidget(btn_ban)
        layout.addStretch(); layout.addLayout(actions)

    def _stat_box(self, val, title):
        f = QFrame(); f.setStyleSheet("background: #1e1e24; border-radius: 6px;")
        v = QVBoxLayout(f); v.setContentsMargins(5,5,5,5); v.setSpacing(0)
        l1 = QLabel(val); l1.setAlignment(Qt.AlignmentFlag.AlignCenter); l1.setStyleSheet("font-weight: bold; font-size: 13px; color: white;")
        l2 = QLabel(title); l2.setAlignment(Qt.AlignmentFlag.AlignCenter); l2.setStyleSheet("font-size: 10px; color: #888;")
        v.addWidget(l1); v.addWidget(l2)
        return f

    def _btn(self, icon, col, tip):
        b = QPushButton(); b.setIcon(qta.icon(icon, color="white")); b.setToolTip(tip)
        b.setFixedSize(32, 32); b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(f"background: {col}; border-radius: 8px; border: none;")
        return b

    def open_note(self):
        d = QDialog(self); d.setWindowTitle("یادداشت خصوصی"); d.setFixedSize(300, 200)
        d.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        d.setStyleSheet("background: #2b2b3d; color: white;")
        l = QVBoxLayout(d)
        t = QTextEdit(); t.setPlaceholderText("یادداشت..."); t.setPlainText(getattr(self.user, 'private_note', "") or "")
        t.setStyleSheet("background: #16161a; border: 1px solid #3a3a4e; border-radius: 8px; padding: 5px;")
        b = QPushButton("ذخیره"); b.setStyleSheet("background: #7f5af0; padding: 8px; border-radius: 8px; font-weight: bold; border: none;")
        b.clicked.connect(lambda: self._save_note(d, t.toPlainText()))
        l.addWidget(QLabel("یادداشت برای این کاربر:")); l.addWidget(t); l.addWidget(b)
        d.exec()

    def _save_note(self, dlg, txt):
        uid = getattr(self.user, 'user_id', None)
        if uid: asyncio.create_task(self._async_note(uid, txt))
        dlg.accept()

    async def _async_note(self, uid, txt):
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: self._db_save_note(uid, txt))
            if hasattr(self.parent_widget.window(), 'show_toast'): self.parent_widget.window().show_toast("یادداشت ذخیره شد.")
            await self.parent_widget.refresh_data()
        except Exception as e: print(e)

    def _db_save_note(self, uid, txt):
        with SessionLocal() as db:
            u = db.query(models.User).filter(models.User.user_id == uid).first()
            if u: u.private_note = txt; db.commit()

    def open_chat(self):
        import webbrowser; uid = getattr(self.user, 'user_id', None)
        if uid: webbrowser.open(f"tg://user?id={uid}")

    def toggle_ban(self):
        is_banned = getattr(self.user, 'is_banned', False)
        if QMessageBox.question(self, "تایید", f"آیا مطمئن هستید؟") == QMessageBox.StandardButton.Yes:
            asyncio.create_task(self._async_ban(not is_banned))

    async def _async_ban(self, status):
        try:
            uid = getattr(self.user, 'user_id', None)
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: self._db_ban(uid, status))
            await self.parent_widget.refresh_data()
        except: pass

    def _db_ban(self, uid, s):
        with SessionLocal() as db:
            u = db.query(models.User).filter(models.User.user_id == uid).first()
            if u: u.is_banned = s; db.commit()

# ==============================================================================
# Main Widget
# ==============================================================================
class UsersWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._data_loaded = False
        self.setup_ui()
        self.search_timer = QTimer(); self.search_timer.setSingleShot(True); self.search_timer.timeout.connect(self.refresh_data)

    def setup_ui(self):
        layout = QVBoxLayout(self); layout.setContentsMargins(20, 20, 20, 20); layout.setSpacing(20)

        # Header
        h_top = QHBoxLayout()
        v_ti = QVBoxLayout()
        t = QLabel("👥 مدیریت مشتریان"); t.setStyleSheet("font-size: 24px; font-weight: 900; color: white;")
        s = QLabel("CRM و مدیریت کاربران ربات"); s.setStyleSheet("color: #94a1b2; font-size: 12px;")
        v_ti.addWidget(t); v_ti.addWidget(s)
        
        self.inp_search = QLineEdit(); self.inp_search.setPlaceholderText("🔍 جستجو نام یا آیدی...")
        self.inp_search.setFixedWidth(250)
        self.inp_search.setStyleSheet("background: #21212e; border: 1px solid #3a3a4e; border-radius: 8px; padding: 10px; color: white;")
        self.inp_search.textChanged.connect(lambda: self.search_timer.start(400))
        
        btn_ref = QPushButton(); btn_ref.setIcon(qta.icon('fa5s.sync-alt', color='white')); btn_ref.setFixedSize(40,40)
        btn_ref.setStyleSheet("background: #2cb67d; border-radius: 8px;"); btn_ref.clicked.connect(self.refresh_data)
        
        h_top.addLayout(v_ti); h_top.addStretch(); h_top.addWidget(self.inp_search); h_top.addWidget(btn_ref)
        layout.addLayout(h_top)

        # Flow Area
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setStyleSheet("background: transparent; border: none;")
        self.container = QWidget()
        self.flow_layout = FlowLayout(self.container, spacing=15)
        scroll.setWidget(self.container)
        layout.addWidget(scroll)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._data_loaded:
            QTimer.singleShot(100, self.refresh_data)
            self._data_loaded = True

    @asyncSlot()
    async def refresh_data(self):
        # پاکسازی
        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        q = self.inp_search.text().lower().strip()
        loop = asyncio.get_running_loop()
        
        try:
            users = await loop.run_in_executor(None, lambda: self._fetch_users(q))
            
            if not users:
                l = QLabel("هیچ کاربری یافت نشد."); l.setStyleSheet("color: #666; font-size: 14px; margin-top: 50px;")
                l.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.flow_layout.addWidget(l)
            else:
                for u in users:
                    self.flow_layout.addWidget(UserCard(u, self))
                    
        except Exception as e: print(e)

    def _fetch_users(self, query):
        with SessionLocal() as db:
            all_users = crud.get_all_users(db)
            res = []
            for u in all_users:
                # Simple search filter
                if query and query not in (u.full_name or "").lower() and query not in str(u.user_id):
                    continue
                
                # Calculate stats (Detached object)
                orders = u.orders
                spent = sum(o.total_amount for o in orders if o.status in ['paid', 'shipped', 'approved'])
                
                obj = type('UserView', (), {
                    "user_id": u.user_id, "full_name": u.full_name,
                    "is_banned": u.is_banned, "private_note": u.private_note,
                    "order_count": len(orders), "total_spent": spent
                })
                res.append(obj)
            
            # Sort by spent desc
            res.sort(key=lambda x: x.total_spent, reverse=True)
            return res