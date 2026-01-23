import asyncio
import logging
import time
from datetime import datetime
from typing import List, Dict, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, 
    QGridLayout, QPushButton, QSizePolicy, QGraphicsDropShadowEffect,
    QComboBox, QScrollArea
)
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QFont, QColor
from qasync import asyncSlot
import qtawesome as qta

# Matplotlib Imports
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# Project Imports
from db.database import get_db
from db import crud

# تلاش برای ایمپورت کتابخانه‌های اصلاح متن فارسی (اختیاری)
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    HAS_RESHAPER = True
except ImportError:
    HAS_RESHAPER = False

logger = logging.getLogger(__name__)

# --- تنظیمات فونت Matplotlib (جلوگیری از وارنینگ) ---
available_fonts = set(f.name for f in fm.fontManager.ttflist)
font_candidates = ["Vazirmatn", "Vazir", "Tahoma", "Segoe UI", "Arial"]
CHOSEN_FONT = "Sans Serif" 

for font in font_candidates:
    if font in available_fonts:
        CHOSEN_FONT = font
        break

plt.rcParams['font.family'] = CHOSEN_FONT

# --- تنظیمات ظاهری (Deep Night Palette) ---
BG_COLOR = "#16161a"
CARD_BG = "#242629"
TEXT_WHITE = "#fffffe"
TEXT_GRAY = "#94a1b2"
ACCENT_PURPLE = "#7f5af0"
ACCENT_GREEN = "#2cb67d"
ACCENT_RED = "#ef4565"

def fix_text(text):
    """اصلاح نمایش متن فارسی در Matplotlib"""
    if HAS_RESHAPER:
        try:
            reshaped_text = arabic_reshaper.reshape(text)
            return get_display(reshaped_text)
        except: return text
    return text

# ==============================================================================
# کامپوننت ۱: نمودار خطی (روند فروش)
# ==============================================================================
class SalesAreaChart(FigureCanvasQTAgg):
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.fig.patch.set_facecolor(CARD_BG)
        
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        self.axes = self.fig.add_subplot(111)
        self.axes.set_facecolor(CARD_BG)

    def update_chart(self, dates: List[str], values: List[int]):
        self.axes.clear()
        plt.rcParams['font.family'] = CHOSEN_FONT
        
        if not dates:
            self.axes.text(0.5, 0.5, fix_text("بدون داده"), color=TEXT_GRAY, ha='center', va='center')
            self.draw()
            return

        x = range(len(dates))
        self.axes.plot(x, values, color=ACCENT_PURPLE, linewidth=2.5, marker='o', markersize=5, markerfacecolor=CARD_BG, markeredgewidth=2)
        self.axes.fill_between(x, values, color=ACCENT_PURPLE, alpha=0.15)
        
        self.axes.spines['top'].set_visible(False)
        self.axes.spines['right'].set_visible(False)
        self.axes.spines['left'].set_visible(False)
        self.axes.spines['bottom'].set_color(TEXT_GRAY)
        self.axes.spines['bottom'].set_alpha(0.3)
        
        self.axes.tick_params(axis='x', colors=TEXT_GRAY, labelsize=9)
        self.axes.tick_params(axis='y', colors=TEXT_GRAY, labelsize=9, left=False)
        self.axes.grid(axis='y', color=TEXT_GRAY, linestyle=':', linewidth=0.5, alpha=0.3)
        self.axes.get_yaxis().set_major_formatter(plt.FuncFormatter(lambda x, p: format(int(x), ',')))
        
        short_dates = [d[5:].replace('-', '/') for d in dates] 
        self.axes.set_xticks(list(x))
        self.axes.set_xticklabels(short_dates)
        
        self.fig.tight_layout()
        self.draw()

# ==============================================================================
# کامپوننت ۲: نمودار دونات (دسته‌بندی‌ها)
# ==============================================================================
class CategoryDonutChart(FigureCanvasQTAgg):
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.fig.patch.set_facecolor(CARD_BG)
        self.axes = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def update_chart(self, labels: List[str], values: List[int]):
        self.axes.clear()
        plt.rcParams['font.family'] = CHOSEN_FONT
        
        if not values or sum(values) == 0:
            self.axes.text(0.5, 0.5, fix_text("بدون داده"), color=TEXT_GRAY, ha='center', va='center')
            self.draw()
            return

        colors = ['#4361ee', '#f72585', '#4cc9f0', '#7209b7', '#3a0ca3', '#4895ef']
        fixed_labels = [fix_text(l) for l in labels]

        wedges, texts, autotexts = self.axes.pie(
            values, labels=fixed_labels, autopct='%1.1f%%', startangle=45,
            colors=colors, pctdistance=0.80, labeldistance=1.1,
            textprops=dict(color=TEXT_GRAY, fontsize=9),
            wedgeprops=dict(width=0.35, edgecolor=CARD_BG, linewidth=2)
        )
        
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontsize(8)
            autotext.set_weight('bold')
        
        self.fig.tight_layout()
        self.draw()

# ==============================================================================
# کامپوننت ۳: ویجت سلامت سیستم
# ==============================================================================
class SystemHealthWidget(QFrame):
    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {CARD_BG}; border-radius: 12px; border: 1px solid {BG_COLOR};")
        self.setFixedHeight(90)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(15)
        
        self.items = {}
        self._add_metric("ping", "پینگ دیتابیس", "fa5s.database", "#4cc9f0", layout)
        self._add_separator(layout)
        self._add_metric("size", "حجم دیتابیس", "fa5s.hdd", "#f72585", layout)
        self._add_separator(layout)
        self._add_metric("status", "وضعیت ربات", "fa5s.robot", "#2cb67d", layout)

    def _add_metric(self, key, title, icon, color, parent_layout):
        container = QWidget()
        l = QHBoxLayout(container)
        l.setContentsMargins(0,0,0,0)
        
        icon_lbl = QLabel()
        icon_lbl.setPixmap(qta.icon(icon, color=color).pixmap(32, 32))
        l.addWidget(icon_lbl)
        
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        val_lbl = QLabel("---")
        val_lbl.setStyleSheet(f"color: {TEXT_WHITE}; font-weight: bold; font-size: 14px;")
        
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"color: {TEXT_GRAY}; font-size: 11px;")
        
        text_layout.addWidget(val_lbl)
        text_layout.addWidget(title_lbl)
        l.addLayout(text_layout)
        
        self.items[key] = val_lbl
        parent_layout.addWidget(container)

    def _add_separator(self, layout):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setStyleSheet("color: #3a3a4e; background-color: #3a3a4e; width: 1px;")
        line.setFixedWidth(1)
        layout.addWidget(line)

    def update_values(self, ping, size, status_text):
        self.items["ping"].setText(f"{ping:.0f} ms")
        self.items["size"].setText(f"{size:.1f} MB")
        self.items["status"].setText(status_text)

# ==============================================================================
# کامپوننت ۴: کارت آمار
# ==============================================================================
class StatCard(QFrame):
    def __init__(self, title, icon_name, color_hex):
        super().__init__()
        self.setFixedHeight(120)
        self.setStyleSheet(f"""
            QFrame {{ 
                background-color: {CARD_BG}; 
                border-radius: 16px; 
                border: 1px solid {BG_COLOR}; 
            }}
            QFrame:hover {{ 
                border: 1px solid {color_hex}; 
                background-color: {CARD_BG};
            }}
        """)
        
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0,0,0,50))
        shadow.setOffset(0, 5)
        self.setGraphicsEffect(shadow)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        text_box = QVBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"color: {TEXT_GRAY}; font-size: 13px; font-weight: 500;")
        
        self.value_lbl = QLabel("---")
        self.value_lbl.setStyleSheet(f"color: {TEXT_WHITE}; font-size: 22px; font-weight: bold;")
        
        text_box.addWidget(title_lbl)
        text_box.addWidget(self.value_lbl)
        text_box.addStretch()
        
        icon_lbl = QLabel()
        icon_lbl.setPixmap(qta.icon(icon_name, color=color_hex).pixmap(28, 28))
        icon_lbl.setFixedSize(56, 56)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(f"background-color: {color_hex}25; border-radius: 14px;")

        layout.addLayout(text_box)
        layout.addStretch()
        layout.addWidget(icon_lbl)

    def set_value(self, value: str):
        self.value_lbl.setText(value)

# ==============================================================================
# کامپوننت ۵: آیتم لیست موجودی کم
# ==============================================================================
class LowStockItem(QWidget):
    def __init__(self, name, count):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        
        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(f"color: {TEXT_WHITE}; font-size: 13px;")
        
        count_lbl = QLabel(f"{count} عدد")
        count_lbl.setStyleSheet(f"color: {ACCENT_RED}; font-weight: bold; font-size: 12px; background: {ACCENT_RED}20; padding: 2px 6px; border-radius: 4px;")
        
        layout.addWidget(name_lbl)
        layout.addStretch()
        layout.addWidget(count_lbl)

# ==============================================================================
# کلاس اصلی: DashboardWidget
# ==============================================================================
class DashboardWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.cards: Dict[str, StatCard] = {}
        
        # فلگ برای جلوگیری از اجرای تکراری یا زودرس
        self._data_loaded = False
        
        self.setup_ui()
        
        # تایمر رفرش خودکار (۵ دقیقه)
        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.timeout.connect(self.refresh_data)
        self.auto_refresh_timer.start(300000)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # --- ۱. هدر ---
        header = QHBoxLayout()
        
        title_box = QVBoxLayout()
        t = QLabel("داشبورد مدیریتی")
        t.setStyleSheet(f"font-size: 22px; font-weight: 900; color: {TEXT_WHITE};")
        self.last_upd = QLabel("درحال بارگذاری...")
        self.last_upd.setStyleSheet(f"color: {TEXT_GRAY}; font-size: 11px;")
        title_box.addWidget(t)
        title_box.addWidget(self.last_upd)
        
        header.addLayout(title_box)
        header.addStretch()

        # ابزارها
        self.combo_period = QComboBox()
        self.combo_period.addItems(["۷ روز اخیر", "۳۰ روز اخیر", "امسال"])
        self.combo_period.setFixedWidth(130)
        self.combo_period.currentIndexChanged.connect(self.refresh_data)
        header.addWidget(self.combo_period)

        # دکمه وضعیت فروشگاه
        self.btn_panic = QPushButton(" وضعیت فروشگاه")
        self.btn_panic.setCheckable(True)
        self.btn_panic.setFixedWidth(160)
        self.btn_panic.setFixedHeight(40)
        self.btn_panic.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_panic.clicked.connect(self.toggle_panic_mode)
        header.addWidget(self.btn_panic)
        
        # دکمه رفرش
        btn_refresh = QPushButton()
        btn_refresh.setIcon(qta.icon('fa5s.sync-alt', color=TEXT_WHITE))
        btn_refresh.setFixedSize(40, 40)
        btn_refresh.setToolTip("بروزرسانی اطلاعات")
        btn_refresh.setStyleSheet(f"background: {CARD_BG}; border: 1px solid {TEXT_GRAY}; border-radius: 8px;")
        btn_refresh.clicked.connect(self.refresh_data)
        header.addWidget(btn_refresh)
        
        main_layout.addLayout(header)

        # --- ۲. کارت‌های آمار ---
        stats_layout = QGridLayout()
        stats_layout.setSpacing(15)
        configs = [
            ("سفارشات جدید", "fa5s.shopping-cart", "#f72585", "pending"),
            ("موجودی کالا", "fa5s.box-open", "#4cc9f0", "products"),
            ("کاربران کل", "fa5s.users", "#7209b7", "users"),
            ("درآمد (تومان)", "fa5s.coins", "#ff9f1c", "revenue")
        ]
        
        for i, (t, ico, col, k) in enumerate(configs):
            c = StatCard(t, ico, col)
            self.cards[k] = c
            stats_layout.addWidget(c, 0, i)
        
        main_layout.addLayout(stats_layout)

        # --- ۳. بدنه اصلی (نمودارها) ---
        mid_layout = QHBoxLayout()
        mid_layout.setSpacing(15)
        
        # ستون راست (نمودار فروش + سلامت) - 65%
        right_col = QVBoxLayout()
        right_col.setSpacing(15)
        
        # ویجت سلامت سیستم
        self.health_widget = SystemHealthWidget()
        right_col.addWidget(self.health_widget)
        
        # نمودار خطی فروش
        chart_frame = QFrame()
        chart_frame.setStyleSheet(f"background: {CARD_BG}; border-radius: 16px; border: 1px solid {BG_COLOR};")
        l1 = QVBoxLayout(chart_frame)
        l1.setContentsMargins(15, 15, 15, 5)
        header_l = QHBoxLayout()
        header_l.addWidget(QLabel("📈 روند فروش", styleSheet=f"color:{TEXT_WHITE}; font-weight:bold; font-size:14px; border:none; background:transparent;"))
        header_l.addStretch()
        l1.addLayout(header_l)
        
        self.chart_sales = SalesAreaChart(width=5, height=3)
        l1.addWidget(self.chart_sales)
        right_col.addWidget(chart_frame)
        
        mid_layout.addLayout(right_col, 65)

        # ستون چپ (دونات + موجودی کم) - 35%
        left_col = QVBoxLayout()
        left_col.setSpacing(15)
        
        # نمودار دسته‌بندی
        donut_frame = QFrame()
        donut_frame.setStyleSheet(f"background: {CARD_BG}; border-radius: 16px; border: 1px solid {BG_COLOR};")
        l2 = QVBoxLayout(donut_frame)
        l2.setContentsMargins(15, 15, 15, 5)
        l2.addWidget(QLabel("📊 دسته‌بندی‌ها", styleSheet=f"color:{TEXT_WHITE}; font-weight:bold; font-size:14px; border:none; background:transparent;"))
        self.chart_cat = CategoryDonutChart(width=4, height=3)
        l2.addWidget(self.chart_cat)
        left_col.addWidget(donut_frame)
        
        # لیست موجودی کم (طراحی جدید)
        stock_frame = QFrame()
        stock_frame.setStyleSheet(f"background: {CARD_BG}; border-radius: 16px; border: 1px solid {BG_COLOR};")
        l3 = QVBoxLayout(stock_frame)
        l3.setContentsMargins(15, 15, 15, 15)
        
        header_stock = QHBoxLayout()
        header_stock.addWidget(QLabel("⚠️ هشدار موجودی", styleSheet=f"color:{ACCENT_RED}; font-weight:bold; font-size:14px; border:none; background:transparent;"))
        header_stock.addStretch()
        l3.addLayout(header_stock)
        
        # کانتینر برای لیست آیتم‌ها
        self.low_stock_container = QWidget()
        self.low_stock_layout = QVBoxLayout(self.low_stock_container)
        self.low_stock_layout.setContentsMargins(0, 10, 0, 0)
        self.low_stock_layout.setSpacing(5)
        
        # اسکرول مخفی برای وقتی لیست طولانی است
        scroll = QScrollArea()
        scroll.setWidget(self.low_stock_container)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        l3.addWidget(scroll)
        
        left_col.addWidget(stock_frame)

        mid_layout.addLayout(left_col, 35)
        main_layout.addLayout(mid_layout)

    def showEvent(self, event):
        """لود دیتا فقط زمانی که ویجت نمایش داده می‌شود"""
        super().showEvent(event)
        if not self._data_loaded:
            # تاخیر کوچک برای جلوگیری از لگ اولیه
            QTimer.singleShot(200, self.refresh_data)
            self._data_loaded = True

    @asyncSlot()
    async def refresh_data(self):
        """دریافت همزمان داده‌ها بدون فریز شدن UI"""
        loop = asyncio.get_running_loop()
        start_time = time.time()

        period_idx = self.combo_period.currentIndex()
        days = 7 if period_idx == 0 else (30 if period_idx == 1 else 365)

        def fetch_all():
            """اجرا در ترد جداگانه برای جلوگیری از لگ"""
            with next(get_db()) as db:
                # 1. آمار کارت‌ها
                p_cnt = crud.get_orders_count_by_status(db, "pending_payment")
                pr_cnt = crud.get_total_product_count(db)
                u_cnt = crud.get_total_user_count(db)
                rev = crud.get_total_revenue(db)
                
                # 2. آمار نمودارها
                sales_trend = crud.get_sales_stats_by_period(db, days)
                cat_stats = crud.get_category_sales_stats(db)
                
                # 3. سیستم و موجودی
                db_size = crud.get_db_size_mb()
                low_stock_objs = crud.get_low_stock_products(db, limit=5)
                # تبدیل آبجکت‌ها به دیکشنری ساده برای انتقال به ترد اصلی
                low_stock_data = [{"name": p.name, "stock": p.stock} for p in low_stock_objs]
                
                # 4. وضعیت فروشگاه
                is_open = crud.get_setting(db, "shop_is_open", "true") == "true"
                
                return p_cnt, pr_cnt, u_cnt, rev, sales_trend, cat_stats, db_size, low_stock_data, is_open

        try:
            # اجرای تابع دیتابیس در Executor
            res = await loop.run_in_executor(None, fetch_all)
            p_cnt, pr_cnt, u_cnt, rev, trend, cats, db_sz, ls_data, is_open = res
            
            # --- بروزرسانی UI ---
            
            # 1. کارت‌ها
            self.cards["pending"].set_value(str(p_cnt))
            self.cards["products"].set_value(str(pr_cnt))
            self.cards["users"].set_value(str(u_cnt))
            self.cards["revenue"].set_value(f"{int(rev):,}")
            
            # 2. نمودارها
            self.chart_sales.update_chart(trend["dates"], trend["values"])
            self.chart_cat.update_chart(cats["labels"], cats["values"])
            
            # 3. سلامت سیستم
            ping = (time.time() - start_time) * 1000
            self.health_widget.update_values(ping, db_sz, "Online" if is_open else "Closed")
            
            # 4. لیست موجودی کم (بازسازی لیست)
            for i in range(self.low_stock_layout.count()):
                item = self.low_stock_layout.itemAt(i)
                if item.widget(): item.widget().deleteLater()
            
            if not ls_data:
                lbl = QLabel("✅ موجودی انبار کامل است")
                lbl.setStyleSheet(f"color: {ACCENT_GREEN}; font-size: 12px; padding: 10px;")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.low_stock_layout.addWidget(lbl)
            else:
                for item in ls_data:
                    self.low_stock_layout.addWidget(LowStockItem(item['name'], item['stock']))
            self.low_stock_layout.addStretch()
                
            # 5. دکمه وضعیت فروشگاه
            self.update_panic_button(is_open)

            self.last_upd.setText(f"بروزرسانی: {datetime.now().strftime('%H:%M:%S')}")

        except Exception as e:
            logger.error(f"Dashboard Update Failed: {e}", exc_info=True)
            self.last_upd.setText("❌ خطا در اتصال")

    def update_panic_button(self, is_open):
        self.btn_panic.blockSignals(True) # جلوگیری از لوپ سیگنال
        if is_open:
            self.btn_panic.setText("🟢 فروشگاه باز است")
            self.btn_panic.setStyleSheet(f"""
                QPushButton {{ 
                    background: {CARD_BG}; 
                    border: 1px solid {ACCENT_GREEN}; 
                    color: {ACCENT_GREEN}; 
                    border-radius: 8px; font-weight: bold; 
                }}
                QPushButton:hover {{ background: {ACCENT_GREEN}; color: white; }}
                QPushButton:checked {{ background: {ACCENT_GREEN}; color: white; }}
            """)
            self.btn_panic.setChecked(True)
        else:
            self.btn_panic.setText("⛔ فروشگاه بسته است")
            self.btn_panic.setStyleSheet(f"""
                QPushButton {{ 
                    background: {ACCENT_RED}; 
                    border: 1px solid {ACCENT_RED}; 
                    color: white; 
                    border-radius: 8px; font-weight: bold; 
                }}
                QPushButton:hover {{ background: #d03e58; }}
            """)
            self.btn_panic.setChecked(False)
        self.btn_panic.blockSignals(False)

    @asyncSlot()
    async def toggle_panic_mode(self):
        """تغییر وضعیت باز/بسته بودن فروشگاه"""
        is_opening = self.btn_panic.isChecked() 
        state_str = "true" if is_opening else "false"
        
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, lambda: crud.set_setting(next(get_db()), "shop_is_open", state_str))
            
            # آپدیت ظاهری
            self.update_panic_button(is_opening)
            
            # ارسال نوتیفیکیشن
            msg = "فروشگاه باز شد." if is_opening else "فروشگاه بسته شد."
            logger.info(f"Shop status changed: {msg}")
                
        except Exception as e:
            logger.error(f"Panic Toggle Error: {e}")
            self.btn_panic.setChecked(not is_opening)