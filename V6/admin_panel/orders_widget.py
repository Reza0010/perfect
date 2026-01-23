import asyncio
import logging
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

# تلاش برای ایمپورت پانداز
try:
    import pandas as pd
except ImportError:
    pd = None

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QFrame, QSizePolicy, QGridLayout, QMessageBox, 
    QFileDialog, QGraphicsDropShadowEffect, QLineEdit, QTextEdit
)
from PyQt6.QtGui import QColor, QFont, QCursor, QTextDocument, QPageSize, QPageLayout
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog, QPrintPreviewDialog
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize, QUrl
from qasync import asyncSlot
import qtawesome as qta

from db.database import SessionLocal, get_db
from db import crud

logger = logging.getLogger(__name__)

# --- رنگ‌بندی و کانفیگ ---
KANBAN_COLUMNS = [
    {"id": "pending_payment", "title": "🟡 در انتظار پرداخت", "color": "#f72585", "bg": "#f7258520", "msg": "سفارش شما ثبت شد و در انتظار پرداخت است."},
    {"id": "approved",        "title": "🟢 تایید شده (آماده‌سازی)", "color": "#4cc9f0", "bg": "#4cc9f020", "msg": "سفارش شما تایید شد و در حال آماده‌سازی است."},
    {"id": "shipped",         "title": "🚚 ارسال شده",        "color": "#4361ee", "bg": "#4361ee20", "msg": "سفارش شما تحویل پست شد."},
    {"id": "rejected",        "title": "❌ رد شده / لغو",     "color": "#ef4565", "bg": "#ef456520", "msg": "سفارش شما لغو شد."},
    {"id": "paid",            "title": "💰 پرداخت شده",       "color": "#2cb67d", "bg": "#2cb67d20", "msg": "پرداخت شما تایید شد."}
]

# ==============================================================================
# کلاس کارت سفارش (Order Card)
# ==============================================================================
class OrderCard(QFrame):
    def __init__(self, order_data: Dict[str, Any], parent_widget):
        super().__init__()
        self.data = order_data # ذخیره کل دیتا برای استفاده‌های بعدی
        self.order_id = order_data['id']
        self.user_name = order_data['user_name']
        self.total_amount = order_data['total_amount']
        self.status = order_data['status']
        self.items_count = order_data.get('items_count', 0)
        self.parent_widget = parent_widget

        self.setObjectName("kanban_card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(180)
        
        col_conf = next((c for c in KANBAN_COLUMNS if c["id"] == self.status), {"color": "#ccc", "bg": "#333"})
        status_color = col_conf["color"]
        status_bg = col_conf["bg"]

        # افکت سایه
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

        self.setStyleSheet(f"""
            QFrame#kanban_card {{
                background-color: #242629;
                border-radius: 12px;
                border-left: 4px solid {status_color};
                border: 1px solid #16161a;
            }}
            QFrame#kanban_card:hover {{
                background-color: #2a2c30;
                border: 1px solid {status_color};
            }}
            QLabel {{ border: none; background: transparent; color: #e4e5f1; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(5)
        
        # 1. هدر کارت (قیمت و ID)
        top_row = QHBoxLayout()
        lbl_price = QLabel(f"{int(self.total_amount):,} ت")
        lbl_price.setStyleSheet(f"font-weight: bold; font-size: 15px; color: {status_color};")
        
        lbl_id = QLabel(f"#{self.order_id}")
        lbl_id.setStyleSheet("font-weight: bold; font-size: 12px; color: #94a1b2; background: #16161a; padding: 2px 6px; border-radius: 4px;")
        
        top_row.addWidget(lbl_price)
        top_row.addStretch()
        top_row.addWidget(lbl_id)
        layout.addLayout(top_row)

        # 2. اطلاعات مشتری
        user_row = QHBoxLayout()
        user_icon = QLabel(); user_icon.setPixmap(qta.icon('fa5s.user', color='#94a1b2').pixmap(14,14))
        lbl_user = QLabel(self.user_name)
        lbl_user.setStyleSheet("font-weight: 500;")
        user_row.addWidget(user_icon)
        user_row.addWidget(lbl_user)
        user_row.addStretch()
        layout.addLayout(user_row)

        # 3. تاریخ و اقلام
        info_row = QHBoxLayout()
        date_str = self.data['created_at'].strftime('%Y/%m/%d')
        lbl_info = QLabel(f"📅 {date_str}  |  📦 {self.items_count} قلم")
        lbl_info.setStyleSheet("color: #94a1b2; font-size: 11px;")
        info_row.addWidget(lbl_info)
        layout.addLayout(info_row)
        
        # خط جداکننده
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #3a3a4e; margin: 4px 0px;")
        layout.addWidget(line)

        # 4. دکمه‌های عملیاتی
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(6)
        
        # دکمه‌های تغییر وضعیت
        if self.status == "pending_payment":
            self._add_btn(actions_layout, "تایید", "#4cc9f0", lambda: self.parent_widget.change_status_safe(self.order_id, "approved"))
            self._add_btn(actions_layout, "رد", "#ef4565", lambda: self.parent_widget.change_status_safe(self.order_id, "rejected"), outline=True)
            
        elif self.status == "approved" or self.status == "paid":
            self._add_btn(actions_layout, "ارسال شد", "#4361ee", lambda: self.parent_widget.change_status_safe(self.order_id, "shipped"))

        actions_layout.addStretch()
        
        # دکمه پرینت فاکتور
        btn_print = QPushButton()
        btn_print.setIcon(qta.icon('fa5s.print', color='#94a1b2'))
        btn_print.setToolTip("چاپ فاکتور رسمی")
        btn_print.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_print.setStyleSheet("background: transparent; border: 1px solid #3a3a4e; border-radius: 6px; padding: 4px;")
        btn_print.clicked.connect(self.handle_print)
        actions_layout.addWidget(btn_print)

        layout.addLayout(actions_layout)

    def _add_btn(self, layout, text, color, callback, outline=False):
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if outline:
            style = f"background: transparent; border: 1px solid {color}; color: {color}; border-radius: 6px; padding: 4px 10px; font-weight: bold; font-size: 11px;"
        else:
            style = f"background: {color}; border: 1px solid {color}; color: #000; border-radius: 6px; padding: 4px 10px; font-weight: bold; font-size: 11px;"
        
        btn.setStyleSheet(style)
        btn.clicked.connect(callback)
        layout.addWidget(btn)

    def handle_print(self):
        """فراخوانی متد پرینت از کلاس والد"""
        self.parent_widget.print_invoice(self.order_id)

# ==============================================================================
# کلاس ستون کانبان (Kanban Column)
# ==============================================================================
class KanbanColumn(QFrame):
    def __init__(self, title, color, bg_color, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{ background-color: #21212e; border-radius: 16px; border: 1px solid #16161a; }}
        """)
        self.setFixedWidth(320)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 15, 10, 10)
        layout.setSpacing(10)
        
        # Header
        header_layout = QHBoxLayout()
        
        # نوار رنگی کوچک
        indicator = QFrame()
        indicator.setFixedSize(4, 20)
        indicator.setStyleSheet(f"background-color: {color}; border-radius: 2px;")
        header_layout.addWidget(indicator)
        
        header_lbl = QLabel(title)
        header_lbl.setStyleSheet(f"color: white; font-weight: bold; font-size: 14px;")
        header_layout.addWidget(header_lbl)
        
        header_layout.addStretch()
        
        self.count_badge = QLabel("0")
        self.count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.count_badge.setFixedSize(24, 24)
        self.count_badge.setStyleSheet(f"background-color: {bg_color}; color: {color}; border-radius: 12px; font-size: 11px; font-weight: bold;")
        header_layout.addWidget(self.count_badge)
        
        layout.addLayout(header_layout)
        
        # Scroll Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        self.cards_container = QWidget()
        self.cards_container.setStyleSheet("background: transparent;")
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setSpacing(10)
        self.cards_layout.setContentsMargins(2, 2, 2, 10)
        self.cards_layout.addStretch()
        
        self.scroll_area.setWidget(self.cards_container)
        layout.addWidget(self.scroll_area)

    def add_card(self, card_widget):
        count = self.cards_layout.count()
        self.cards_layout.insertWidget(count - 1, card_widget)
        self.update_count()

    def clear_all(self):
        while self.cards_layout.count() > 1:
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.update_count()

    def update_count(self):
        count = self.cards_layout.count() - 1
        self.count_badge.setText(str(count))


# ==============================================================================
# کلاس اصلی: OrdersWidget
# ==============================================================================
class OrdersWidget(QWidget):
    def __init__(self, bot_app=None):
        super().__init__()
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.bot_app = bot_app
        self.columns_map = {}
        self.all_orders_cache = [] # کش کردن دیتا برای سرچ سریع
        
        self.setup_ui()
        self._data_loaded = False

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # --- 1. هدر ---
        header_layout = QHBoxLayout()
        
        title_box = QVBoxLayout()
        title = QLabel("📦 مدیریت سفارشات")
        title.setStyleSheet("font-size: 22px; font-weight: 900; color: white;")
        subtitle = QLabel("نمای کانبان (Kanban Board)")
        subtitle.setStyleSheet("color: #94a1b2; font-size: 12px;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header_layout.addLayout(title_box)
        
        header_layout.addStretch()

        # فیلد جستجو
        self.search_inp = QLineEdit()
        self.search_inp.setPlaceholderText("🔍 جستجو (نام، ID)...")
        self.search_inp.setFixedWidth(200)
        self.search_inp.setStyleSheet("""
            QLineEdit { background: #21212e; border: 1px solid #3a3a4e; border-radius: 8px; padding: 8px; color: white; }
            QLineEdit:focus { border: 1px solid #7f5af0; }
        """)
        self.search_inp.textChanged.connect(self.filter_cards)
        header_layout.addWidget(self.search_inp)
        
        # دکمه رفرش
        self.btn_refresh = QPushButton()
        self.btn_refresh.setIcon(qta.icon('fa5s.sync-alt', color='white'))
        self.btn_refresh.setFixedSize(40, 40)
        self.btn_refresh.setStyleSheet("background-color: #3a3a4e; border-radius: 8px;")
        self.btn_refresh.clicked.connect(self.refresh_data)
        header_layout.addWidget(self.btn_refresh)
        
        # دکمه اکسل
        btn_export = QPushButton(" اکسل")
        btn_export.setIcon(qta.icon('fa5s.file-excel', color='white'))
        btn_export.setStyleSheet("background-color: #2cb67d; color: white; border: none; border-radius: 8px; padding: 8px 15px; font-weight: bold;")
        btn_export.clicked.connect(self.export_to_excel)
        header_layout.addWidget(btn_export)
        
        main_layout.addLayout(header_layout)

        # --- 2. کانبان بورد ---
        scroll_container = QScrollArea()
        scroll_container.setWidgetResizable(True)
        scroll_container.setStyleSheet("background: transparent; border: none;")
        
        board_widget = QWidget()
        self.board_layout = QHBoxLayout(board_widget)
        self.board_layout.setSpacing(15)
        self.board_layout.setContentsMargins(0, 10, 0, 10)
        self.board_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        for col_conf in KANBAN_COLUMNS:
            col_widget = KanbanColumn(col_conf["title"], col_conf["color"], col_conf["bg"], self)
            self.columns_map[col_conf["id"]] = col_widget
            self.board_layout.addWidget(col_widget)
        
        self.board_layout.addStretch()
        scroll_container.setWidget(board_widget)
        main_layout.addWidget(scroll_container)
        
    def showEvent(self, event):  # <-- این متد را به کلاس اضافه کنید
        super().showEvent(event)
        if not self._data_loaded:
            QTimer.singleShot(100, self.refresh_data) # یا refresh_data_slot
            self._data_loaded = True    

    @asyncSlot()
    async def refresh_data(self):
        """رفرش کامل دیتا"""
        self.btn_refresh.setEnabled(False)
        self.search_inp.clear()
        
        # پاکسازی
        for col in self.columns_map.values():
            col.clear_all()
            
        loop = asyncio.get_running_loop()
        try:
            def fetch():
                with next(get_db()) as db:
                    orders = crud.get_filtered_orders(db, status="all")
                    res = []
                    for o in orders:
                        user_name = o.user.full_name if o.user else "Unknown"
                        res.append({
                            "id": o.id,
                            "user_id": o.user_id,
                            "user_name": user_name,
                            "total_amount": o.total_amount,
                            "status": o.status,
                            "created_at": o.created_at,
                            "items_count": len(o.items) if o.items else 0
                        })
                    return res
            
            self.all_orders_cache = await loop.run_in_executor(None, fetch)
            
            # بازسازی کارت‌ها
            for data in self.all_orders_cache:
                self._add_card_to_column(data)
                    
        except Exception as e:
            logger.error(f"Refresh Error: {e}")
            if hasattr(self.window(), 'show_toast'):
                self.window().show_toast("خطا در دریافت اطلاعات", is_error=True)
        finally:
            self.btn_refresh.setEnabled(True)

    def _add_card_to_column(self, data):
        status = data['status']
        if status in self.columns_map:
            card = OrderCard(data, self)
            self.columns_map[status].add_card(card)

    def filter_cards(self, text):
        """فیلتر کلاینت‌ساید کارت‌ها بدون درخواست به دیتابیس"""
        text = text.lower().strip()
        # پاکسازی بورد
        for col in self.columns_map.values():
            col.clear_all()
            
        for data in self.all_orders_cache:
            if text in str(data['id']) or text in data['user_name'].lower():
                self._add_card_to_column(data)

    def change_status_safe(self, order_id, new_status):
        asyncio.create_task(self.update_order_status(order_id, new_status))

    async def update_order_status(self, order_id, new_status):
        loop = asyncio.get_running_loop()
        try:
            def db_op():
                with next(get_db()) as db:
                    return crud.update_order_status(db, order_id, new_status)
            
            updated_order = await loop.run_in_executor(None, db_op)
            
            if updated_order and self.bot_app:
                col_conf = next((c for c in KANBAN_COLUMNS if c["id"] == new_status), {})
                msg_text = col_conf.get("msg", "")
                try:
                    await self.bot_app.bot.send_message(
                        chat_id=updated_order.user_id,
                        text=f"🔔 **وضعیت سفارش #{order_id} تغییر کرد**\n\n{msg_text}",
                        parse_mode="Markdown"
                    )
                except:
                    pass
            
            await self.refresh_data()
            if hasattr(self.window(), 'show_toast'):
                self.window().show_toast(f"سفارش #{order_id} بروزرسانی شد.")
                
        except Exception as e:
            QMessageBox.critical(self, "خطا", f"{e}")

    # ==========================================================================
    # 🖨️ سیستم تولید و پرینت فاکتور (Invoice System)
    # ==========================================================================
    def print_invoice(self, order_id):
        """تولید HTML فاکتور و نمایش دیالوگ پرینت"""
        
        # 1. دریافت جزئیات کامل سفارش
        # نکته: چون async نیست (پرینت نیاز به GUI Thread دارد)، از ترد اصلی اجرا می‌کنیم
        # اما کوئری دیتابیس باید سریع باشد.
        try:
            with next(get_db()) as db:
                order = crud.get_order_by_id(db, order_id)
                if not order:
                    return
                
                # تبدیل اقلام به لیست
                items = []
                for item in order.items:
                    items.append({
                        "name": item.product.name if item.product else "محصول حذف شده",
                        "qty": item.quantity,
                        "price": item.unit_price,
                        "total": item.quantity * item.unit_price
                    })
                
                user_info = {
                    "name": order.user.full_name if order.user else "Unknown",
                    "phone": order.user.phone_number if order.user else "-",
                    "address": order.user.saved_address if order.user else "-"
                }
                
                date_str = order.created_at.strftime("%Y/%m/%d - %H:%M")
                total = order.total_amount
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Database error: {e}")
            return

        # 2. تولید HTML فاکتور
        html_content = self._generate_invoice_html(order_id, date_str, user_info, items, total)

        # 3. نمایش پیش‌نمایش پرینت
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        
        preview = QPrintPreviewDialog(printer, self)
        preview.setWindowTitle(f"چاپ فاکتور سفارش #{order_id}")
        preview.setMinimumSize(1000, 800)
        
        # اتصال تابع رندر به سیگنال paintRequested
        def handle_paint(printer_obj):
            doc = QTextDocument()
            # تنظیم فونت داکیومنت
            font = QFont("Vazirmatn", 10) 
            doc.setDefaultFont(font)
            doc.setHtml(html_content)
            doc.print(printer_obj)

        preview.paintRequested.connect(handle_paint)
        preview.exec()

    def _generate_invoice_html(self, order_id, date, user, items, total):
        """ساخت کد HTML برای فاکتور زیبا"""
        
        rows = ""
        for idx, item in enumerate(items, 1):
            rows += f"""
            <tr>
                <td style="text-align: center;">{idx}</td>
                <td>{item['name']}</td>
                <td style="text-align: center;">{item['qty']}</td>
                <td style="text-align: right;">{int(item['price']):,}</td>
                <td style="text-align: right;">{int(item['total']):,}</td>
            </tr>
            """
            
        html = f"""
        <!DOCTYPE html>
        <html dir="rtl" lang="fa">
        <head>
            <style>
                body {{ font-family: 'Vazirmatn', 'Tahoma', sans-serif; padding: 20px; color: #333; }}
                .header {{ text-align: center; margin-bottom: 30px; border-bottom: 2px solid #444; padding-bottom: 10px; }}
                .header h1 {{ margin: 0; font-size: 24px; color: #2c3e50; }}
                .header p {{ margin: 5px 0; color: #7f8c8d; }}
                
                .info-box {{ display: flex; justify-content: space-between; margin-bottom: 20px; }}
                .info-table {{ width: 100%; margin-bottom: 20px; border-collapse: collapse; }}
                .info-table td {{ padding: 5px; }}
                
                .items-table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                .items-table th {{ background-color: #2c3e50; color: white; padding: 10px; border: 1px solid #2c3e50; }}
                .items-table td {{ padding: 10px; border: 1px solid #ddd; }}
                .items-table tr:nth-child(even) {{ background-color: #f2f2f2; }}
                
                .total-section {{ float: left; margin-top: 20px; width: 300px; }}
                .total-table {{ width: 100%; border-collapse: collapse; }}
                .total-table td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
                .total-price {{ font-size: 18px; font-weight: bold; color: #e74c3c; }}
                
                .footer {{ margin-top: 50px; text-align: center; font-size: 12px; color: #7f8c8d; border-top: 1px solid #ddd; padding-top: 10px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>فاکتور فروش</h1>
                <p>فروشگاه آنلاین تلگرامی</p>
                <p>تاریخ صدور: {date}</p>
            </div>
            
            <table class="info-table">
                <tr>
                    <td width="50%"><strong>خریدار:</strong> {user['name']}</td>
                    <td width="50%"><strong>شماره سفارش:</strong> #{order_id}</td>
                </tr>
                <tr>
                    <td><strong>تلفن:</strong> {user['phone']}</td>
                    <td><strong>آدرس:</strong> {user['address']}</td>
                </tr>
            </table>
            
            <table class="items-table">
                <thead>
                    <tr>
                        <th width="5%">#</th>
                        <th width="50%">شرح کالا</th>
                        <th width="10%">تعداد</th>
                        <th width="15%">فی (تومان)</th>
                        <th width="20%">جمع کل (تومان)</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
            
            <div class="total-section">
                <table class="total-table">
                    <tr>
                        <td>جمع کل:</td>
                        <td style="text-align: left;">{int(total):,} تومان</td>
                    </tr>
                    <tr>
                        <td><strong>مبلغ قابل پرداخت:</strong></td>
                        <td style="text-align: left;" class="total-price">{int(total):,} تومان</td>
                    </tr>
                </table>
            </div>
            
            <div style="clear: both;"></div>
            
            <div class="footer">
                <p>از خرید شما سپاسگزاریم.</p>
                <p>این فاکتور به صورت سیستمی صادر شده و فاقد مهر و امضا می‌باشد.</p>
            </div>
        </body>
        </html>
        """
        return html

    @asyncSlot()
    async def export_to_excel(self):
        if pd is None:
            QMessageBox.warning(self, "خطا", "کتابخانه pandas نصب نیست.")
            return
            
        file_path, _ = QFileDialog.getSaveFileName(self, "ذخیره اکسل", "Orders.xlsx", "Excel (*.xlsx)")
        if not file_path: return

        loop = asyncio.get_running_loop()
        try:
            def save():
                data = self.all_orders_cache # استفاده از کش
                if not data: return False
                df = pd.DataFrame(data)
                # تغییر نام ستون‌ها برای خروجی زیباتر
                df.rename(columns={
                    "id": "شناسه", "user_name": "نام مشتری", 
                    "total_amount": "مبلغ", "status": "وضعیت", 
                    "created_at": "تاریخ"
                }, inplace=True)
                df.to_excel(file_path, index=False)
                return True
            
            res = await loop.run_in_executor(None, save)
            if res:
                if hasattr(self.window(), 'show_toast'):
                    self.window().show_toast("فایل اکسل ذخیره شد.")
            else:
                QMessageBox.warning(self, "توجه", "داده‌ای برای ذخیره وجود ندارد.")
        except Exception as e:
            QMessageBox.critical(self, "خطا", str(e))