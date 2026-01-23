import asyncio
import shutil
import logging
import os
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QPushButton, QComboBox, QSpinBox, QMessageBox, QDoubleSpinBox,
    QFileDialog, QCheckBox, QScrollArea, QFrame, QGridLayout, 
    QGraphicsDropShadowEffect, QSizePolicy, QButtonGroup, QAbstractSpinBox,
    QApplication, QMenu, QTableWidget, QTableWidgetItem, QHeaderView, 
    QInputDialog, QAbstractItemView, QTabWidget, QDialog
)
from PyQt6.QtGui import QPixmap, QDragEnterEvent, QDropEvent, QColor, QAction, QCursor, QFont, QDoubleValidator, QIcon
from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal, QEvent
from qasync import asyncSlot
import qtawesome as qta

# Import Project Modules
from db.database import get_db
from db import crud
from config import BASE_DIR, MEDIA_PRODUCTS_DIR

logger = logging.getLogger(__name__)

# ==============================================================================
# Helper Widgets (Input Utils)
# ==============================================================================
class FormattedPriceInput(QLineEdit):
    """ورودی عدد با جداکننده هزارگان و رنگ‌بندی بهینه"""
    def __init__(self, parent=None, is_discount=False):
        super().__init__(parent)
        self.setPlaceholderText("0")
        
        validator = QDoubleValidator(0.0, 999_999_999_999.0, 0)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.setValidator(validator)
        
        self.textChanged.connect(self.format_text)
        
        text_color = "#f1c40f" if is_discount else "#2cb67d" # زرد برای تخفیف، سبز برای قیمت
        self.setStyleSheet(f"""
            QLineEdit {{
                background: #16161a;
                border: 1px solid #3a3a4e;
                border-radius: 8px;
                padding: 10px;
                color: {text_color};
                font-weight: bold;
                font-size: 14px;
            }}
            QLineEdit:focus {{ border: 1px solid {text_color}; }}
            QLineEdit::placeholder {{ color: #555; }}
        """)

    def format_text(self, text):
        if not text: return
        clean_text = text.replace(",", "")
        if not clean_text.isdigit(): return
        
        try:
            val = int(clean_text)
            formatted = "{:,}".format(val)
            if text != formatted:
                self.blockSignals(True)
                self.setText(formatted)
                self.setCursorPosition(len(formatted))
                self.blockSignals(False)
        except: pass

    def value(self) -> int:
        text = self.text().replace(",", "")
        return int(text) if text else 0

    def setValue(self, val):
        self.setText("{:,}".format(int(val)))

class TagsInput(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("مثال: جدید, فروش ویژه, تابستانه")
        self.setStyleSheet("""
            QLineEdit { background: #16161a; border: 1px solid #3a3a4e; border-radius: 8px; padding: 10px; color: #e4e5f1; }
            QLineEdit:focus { border-color: #7f5af0; }
        """)
    
    def get_tags_list(self) -> List[str]:
        text = self.text().strip()
        if not text: return []
        return [t.strip() for t in text.split(',') if t.strip()]

    def set_tags(self, tags_str: str):
        self.setText(tags_str if tags_str else "")

class ImageDropZone(QLabel):
    imageDropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setText("📷\nتصویر را اینجا رها کنید\nیا کلیک کنید")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(220)
        self.default_style = """
            QLabel { border: 2px dashed #4a4a62; border-radius: 12px; background: #21212e; color: #94a1b2; font-weight: bold; }
            QLabel:hover { border-color: #7f5af0; background: #262635; color: white; }
        """
        self.setStyleSheet(self.default_style)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.accept()
            self.setStyleSheet("border: 2px dashed #2cb67d; background: #262635; color: #2cb67d;")
        else: event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self.default_style)

    def dropEvent(self, event: QDropEvent):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        if files:
            path = files[0]
            if path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                self.imageDropped.emit(path)
                self.set_image(path)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            f, _ = QFileDialog.getOpenFileName(self, "انتخاب تصویر", "", "Images (*.png *.jpg *.jpeg *.webp)")
            if f:
                self.imageDropped.emit(f)
                self.set_image(f)

    def set_image(self, path):
        if os.path.exists(path):
            pix = QPixmap(path)
            self.setPixmap(pix.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.setStyleSheet("border: 2px solid #7f5af0; border-radius: 12px; background: #16161a;")
        else: self.reset()

    def reset(self):
        self.clear()
        self.setText("📷\nتصویر را اینجا رها کنید\nیا کلیک کنید")
        self.setStyleSheet(self.default_style)

class VariantManager(QTableWidget):
    def __init__(self):
        super().__init__(0, 4)
        self.setHorizontalHeaderLabels(["نام متغیر (رنگ/سایز)", "تفاوت قیمت (+/-)", "موجودی", "حذف"])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet("""
            QTableWidget { background: #16161a; border: 1px solid #3a3a4e; border-radius: 8px; color: white; gridline-color: #333; }
            QHeaderView::section { background: #2b2b3d; color: #a6accd; padding: 8px; border: none; font-weight: bold; }
        """)

    def add_row(self, name="", price_adj=0, stock=0):
        row = self.rowCount()
        self.insertRow(row)
        
        inp_name = QLineEdit(name)
        inp_name.setPlaceholderText("مثال: قرمز")
        inp_name.setStyleSheet("background: #21212e; color: white; border: none; padding: 5px;")
        self.setCellWidget(row, 0, inp_name)
        
        inp_price = FormattedPriceInput(is_discount=True) # استفاده از رنگ زرد برای تمایز
        inp_price.setValue(price_adj)
        inp_price.setStyleSheet("background: #21212e; color: #f1c40f; border: none; font-weight: bold;")
        self.setCellWidget(row, 1, inp_price)
        
        inp_stock = QSpinBox()
        inp_stock.setRange(0, 100000)
        inp_stock.setValue(stock)
        inp_stock.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        inp_stock.setStyleSheet("background: #21212e; color: white; border: none; padding: 5px;")
        self.setCellWidget(row, 2, inp_stock)
        
        btn_del = QPushButton()
        btn_del.setIcon(qta.icon('fa5s.trash-alt', color='#ef4565'))
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setStyleSheet("background: transparent; border: none;")
        btn_del.clicked.connect(lambda: self.removeRow(self.indexAt(btn_del.pos()).row()))
        self.setCellWidget(row, 3, btn_del)

    def get_data(self) -> List[dict]:
        variants = []
        for i in range(self.rowCount()):
            name_widget = self.cellWidget(i, 0)
            price_widget = self.cellWidget(i, 1)
            stock_widget = self.cellWidget(i, 2)
            
            if name_widget and name_widget.text().strip():
                variants.append({
                    "name": name_widget.text().strip(),
                    "price_adjustment": price_widget.value(),
                    "stock": stock_widget.value()
                })
        return variants

# ==============================================================================
# Dialog: پنجره ویرایش/افزودن محصول (مستقل)
# ==============================================================================
class ProductEditorDialog(QDialog):
    """دیالوگ مودال برای ویرایش و افزودن محصول"""
    product_saved = pyqtSignal() # سیگنال موفقیت

    def __init__(self, parent=None, product_id=None):
        super().__init__(parent)
        self.product_id = product_id
        self.uploaded_image_path = None
        
        self.setWindowTitle("مدیریت محصول" if product_id else "افزودن محصول جدید")
        self.resize(950, 750)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        # استایل کلی دیالوگ
        self.setStyleSheet("""
            QDialog { background-color: #1c1c24; }
            QLabel { color: #e4e5f1; }
            QTabWidget::pane { border: 1px solid #3a3a4e; border-radius: 8px; background: #21212e; }
            QTabBar::tab { background: transparent; color: #94a1b2; padding: 10px 20px; font-weight: bold; font-size: 13px; }
            QTabBar::tab:selected { color: #7f5af0; border-bottom: 3px solid #7f5af0; }
            QTabBar::tab:hover { color: white; }
        """)

        self.setup_ui()
        
        if product_id:
            asyncio.create_task(self.load_data(product_id))

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header Title
        title = "✏️ ویرایش محصول" if self.product_id else "➕ محصول جدید"
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size: 22px; font-weight: bold; color: white; margin-bottom: 10px;")
        layout.addWidget(lbl_title)

        # Tabs
        self.tabs = QTabWidget()
        
        # Tab 1: مشخصات پایه
        tab_basic = QWidget()
        l_basic = QHBoxLayout(tab_basic) # دو ستونه برای استفاده بهتر از فضا
        
        col_img = QVBoxLayout()
        self.drop_zone = ImageDropZone()
        self.drop_zone.imageDropped.connect(lambda p: setattr(self, 'uploaded_image_path', p))
        col_img.addWidget(self.drop_zone)
        col_img.addStretch()
        
        col_form = QVBoxLayout()
        self.inp_name = QLineEdit(); self.inp_name.setPlaceholderText("نام کامل محصول")
        self.inp_cat = QComboBox()
        self.inp_brand = QLineEdit(); self.inp_brand.setPlaceholderText("برند (مثال: سامسونگ)")
        self.inp_desc = QTextEdit(); self.inp_desc.setPlaceholderText("توضیحات کامل محصول..."); self.inp_desc.setMinimumHeight(150)
        
        for w in [self.inp_name, self.inp_cat, self.inp_brand, self.inp_desc]:
            w.setStyleSheet("background: #16161a; color: white; border: 1px solid #3a3a4e; padding: 10px; border-radius: 8px;")
        
        col_form.addWidget(QLabel("نام محصول:"))
        col_form.addWidget(self.inp_name)
        col_form.addWidget(QLabel("دسته‌بندی:"))
        col_form.addWidget(self.inp_cat)
        col_form.addWidget(QLabel("برند:"))
        col_form.addWidget(self.inp_brand)
        col_form.addWidget(QLabel("توضیحات:"))
        col_form.addWidget(self.inp_desc)

        l_basic.addLayout(col_img, 1)
        l_basic.addLayout(col_form, 2)
        
        # Tab 2: قیمت و موجودی
        tab_price = QWidget()
        l_price = QVBoxLayout(tab_price)
        l_price.setContentsMargins(30,30,30,30); l_price.setSpacing(20)
        
        self.inp_price = FormattedPriceInput()
        self.inp_discount = FormattedPriceInput(is_discount=True)
        self.inp_stock = QSpinBox(); self.inp_stock.setRange(0, 100000); self.inp_stock.setStyleSheet("background: #16161a; color: white; border: 1px solid #3a3a4e; padding: 10px; border-radius: 8px;")
        self.chk_top = QCheckBox("نمایش در لیست پرفروش‌ها")
        self.chk_top.setStyleSheet("color: white; font-weight: bold;")

        l_price.addWidget(QLabel("قیمت اصلی (تومان):"))
        l_price.addWidget(self.inp_price)
        l_price.addWidget(QLabel("قیمت با تخفیف (اختیاری):"))
        l_price.addWidget(self.inp_discount)
        l_price.addWidget(QLabel("موجودی انبار:"))
        l_price.addWidget(self.inp_stock)
        l_price.addWidget(self.chk_top)
        l_price.addStretch()
        
        # Tab 3: متغیرها
        tab_vars = QWidget()
        l_vars = QVBoxLayout(tab_vars)
        self.variant_mgr = VariantManager()
        btn_add_var = QPushButton(" افزودن متغیر جدید")
        btn_add_var.setIcon(qta.icon('fa5s.plus', color='#2cb67d'))
        btn_add_var.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add_var.setStyleSheet("background: #21212e; border: 1px dashed #2cb67d; color: #2cb67d; border-radius: 8px; padding: 10px; font-weight: bold;")
        btn_add_var.clicked.connect(lambda: self.variant_mgr.add_row())
        
        l_vars.addWidget(QLabel("مدیریت رنگ و سایز (اختیاری):", styleSheet="color:#7f5af0; font-weight:bold;"))
        l_vars.addWidget(self.variant_mgr)
        l_vars.addWidget(btn_add_var)

        # Tab 4: سئو و تگ‌ها
        tab_extra = QWidget()
        l_extra = QVBoxLayout(tab_extra)
        l_extra.setContentsMargins(30,30,30,30)
        self.inp_tags = TagsInput()
        self.inp_rel = QLineEdit()
        self.inp_rel.setPlaceholderText("مثال: 12, 45, 89")
        self.inp_rel.setStyleSheet("background: #16161a; color: white; border: 1px solid #3a3a4e; padding: 10px; border-radius: 8px;")
        
        l_extra.addWidget(QLabel("برچسب‌ها (Tags):"))
        l_extra.addWidget(self.inp_tags)
        l_extra.addWidget(QLabel("شناسه محصولات مرتبط (Related IDs):"))
        l_extra.addWidget(self.inp_rel)
        l_extra.addStretch()

        self.tabs.addTab(tab_basic, "اصلی")
        self.tabs.addTab(tab_price, "قیمت و موجودی")
        self.tabs.addTab(tab_vars, "تنوع محصول")
        self.tabs.addTab(tab_extra, "دیگر")
        
        layout.addWidget(self.tabs)

        # Footer Buttons
        btn_box = QHBoxLayout()
        btn_cancel = QPushButton("انصراف")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet("background: #3a3a4e; color: white; padding: 10px 20px; border-radius: 8px; border: none;")
        btn_cancel.clicked.connect(self.reject)
        
        btn_save = QPushButton("ذخیره محصول")
        btn_save.setIcon(qta.icon('fa5s.save', color='white'))
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setStyleSheet("background: #7f5af0; color: white; padding: 10px 25px; border-radius: 8px; font-weight: bold; border: none;")
        btn_save.clicked.connect(self.save_product)
        
        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_save)
        layout.addLayout(btn_box)
        
        # Load Categories Immediately
        self.load_categories()

    def load_categories(self):
        """پر کردن کمبوباکس دسته‌ها"""
        # نکته: چون نمی‌توانیم async را در init صبر کنیم، این را synchronous اجرا می‌کنیم یا تسک می‌کنیم
        # برای سادگی در UI Thread:
        try:
            with next(get_db()) as db:
                cats = crud.get_all_categories(db)
                self.inp_cat.clear()
                for c in cats:
                    self.inp_cat.addItem(c.name, c.id)
        except Exception: pass

    async def load_data(self, pid):
        """لود دیتای محصول برای ویرایش"""
        loop = asyncio.get_running_loop()
        p = await loop.run_in_executor(None, lambda: crud.get_product(next(get_db()), pid))
        if not p: return

        self.inp_name.setText(p.name)
        self.inp_price.setValue(float(p.price))
        self.inp_discount.setValue(float(p.discount_price or 0))
        self.inp_stock.setValue(p.stock)
        self.inp_brand.setText(p.brand or "")
        self.inp_desc.setPlainText(p.description or "")
        self.inp_tags.set_tags(p.tags or "")
        self.inp_rel.setText(p.related_product_ids or "")
        self.chk_top.setChecked(p.is_top_seller)
        
        idx = self.inp_cat.findData(p.category_id)
        if idx >= 0: self.inp_cat.setCurrentIndex(idx)
        
        if p.image_path:
            full_p = BASE_DIR / p.image_path
            self.uploaded_image_path = str(full_p)
            self.drop_zone.set_image(self.uploaded_image_path)
            
        for v in p.variants:
            self.variant_mgr.add_row(v.name, v.price_adjustment, v.stock)

    @asyncSlot()
    async def save_product(self):
        if not self.inp_name.text():
            return QMessageBox.warning(self, "خطا", "نام محصول الزامی است.")

        # ساخت دیکشنری دیتا
        data = {
            "name": self.inp_name.text(),
            "category_id": self.inp_cat.currentData(),
            "price": self.inp_price.value(),
            "discount_price": self.inp_discount.value(),
            "stock": self.inp_stock.value(),
            "brand": self.inp_brand.text(),
            "description": self.inp_desc.toPlainText(),
            "tags": ",".join(self.inp_tags.get_tags_list()),
            "related_product_ids": self.inp_rel.text(),
            "is_top_seller": self.chk_top.isChecked()
        }
        
        # کپی تصویر
        if self.uploaded_image_path:
            # چک کنیم اگر مسیر قبلاً در مدیا نیست، کپی کنیم
            if str(MEDIA_PRODUCTS_DIR) not in os.path.abspath(self.uploaded_image_path):
                ext = Path(self.uploaded_image_path).suffix
                fname = f"prod_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
                dest = MEDIA_PRODUCTS_DIR / fname
                try:
                    shutil.copy(self.uploaded_image_path, dest)
                    data["image_path"] = f"media/products/{fname}"
                except Exception as e: logger.error(e)

        variants = self.variant_mgr.get_data()
        
        loop = asyncio.get_running_loop()
        try:
            def db_op():
                with next(get_db()) as db:
                    if self.product_id:
                        crud.update_product_with_variants(db, self.product_id, data, variants)
                    else:
                        crud.create_product_with_variants(db, data, variants)
            
            await loop.run_in_executor(None, db_op)
            
            self.product_saved.emit() # اطلاع به والد
            self.accept() # بستن دیالوگ
            
        except Exception as e:
            QMessageBox.critical(self, "خطا", f"مشکلی در ذخیره پیش آمد:\n{e}")

# ==============================================================================
# Card Widget
# ==============================================================================
class ProductCard(QFrame):
    selectionChanged = pyqtSignal(int, bool)

    def __init__(self, product, parent_widget):
        super().__init__()
        self.product = product
        self.p_widget = parent_widget
        self.setFixedSize(260, 390)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._selected = False
        
        self.default_style = """
            QFrame#card { background-color: #242629; border-radius: 14px; border: 1px solid #2b2c37; }
            QFrame#card:hover { border-color: #7f5af0; background-color: #2a2c30; }
        """
        self.selected_style = """
            QFrame#card { background-color: #2a2c30; border-radius: 14px; border: 2px solid #2cb67d; }
        """
        self.setObjectName("card")
        self.setStyleSheet(self.default_style)
        
        # Shadow
        shadow = QGraphicsDropShadowEffect(); shadow.setBlurRadius(15); shadow.setColor(QColor(0,0,0,80)); shadow.setOffset(0,4)
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)

        # Image Area
        img_container = QWidget(); img_container.setFixedHeight(180)
        img_layout = QVBoxLayout(img_container); img_layout.setContentsMargins(0,0,0,0)
        self.img_lbl = QLabel(); self.img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_lbl.setStyleSheet("background-color: #1b1b22; border-top-left-radius: 13px; border-top-right-radius: 13px;")
        
        if product.image_path:
            full_path = BASE_DIR / product.image_path
            if full_path.exists():
                pix = QPixmap(str(full_path))
                self.img_lbl.setPixmap(pix.scaled(260, 180, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
            else: self.img_lbl.setText("📷")
        else: self.img_lbl.setText("📷")
        
        self.chk_select = QCheckBox(img_container)
        self.chk_select.move(12, 12); self.chk_select.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_select.stateChanged.connect(self.on_checked)
        self.chk_select.setStyleSheet("QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px; background: rgba(0,0,0,0.5); border: 1px solid #777; } QCheckBox::indicator:checked { background: #2cb67d; border: 1px solid #2cb67d; }")
        
        img_layout.addWidget(self.img_lbl)
        layout.addWidget(img_container)

        # Info Area
        content = QWidget(); c_layout = QVBoxLayout(content); c_layout.setContentsMargins(15, 12, 15, 15); c_layout.setSpacing(6)
        
        lbl_name = QLabel(product.name); lbl_name.setWordWrap(True); lbl_name.setFixedHeight(40)
        lbl_name.setStyleSheet("font-weight: bold; font-size: 14px; color: #fffffe; line-height: 1.2;")
        
        cat_name = product.category.name if product.category else "دسته‌بندی نشده"
        lbl_meta = QLabel(f"{cat_name}"); lbl_meta.setStyleSheet("color: #94a1b2; font-size: 11px;")
        
        row_info = QHBoxLayout()
        # نمایش قیمت با تخفیف اگر وجود دارد
        if product.discount_price and product.discount_price > 0:
             lbl_price = QLabel(f"{int(product.discount_price):,} ت"); lbl_price.setStyleSheet("color: #f1c40f; font-weight: bold; font-size: 15px;")
             lbl_old = QLabel(f"{int(product.price):,}"); lbl_old.setStyleSheet("color: #666; font-size: 11px; text-decoration: line-through;")
             row_info.addWidget(lbl_price); row_info.addWidget(lbl_old)
        else:
             lbl_price = QLabel(f"{int(product.price):,} ت"); lbl_price.setStyleSheet("color: #2cb67d; font-weight: bold; font-size: 15px;")
             row_info.addWidget(lbl_price)

        stock_col = "#ef4565" if product.stock == 0 else ("#f1c40f" if product.stock < 5 else "#94a1b2")
        lbl_stock = QLabel(f"📦 {product.stock}"); lbl_stock.setStyleSheet(f"color: {stock_col}; font-size: 12px;")
        row_info.addStretch(); row_info.addWidget(lbl_stock)
        
        c_layout.addWidget(lbl_name); c_layout.addWidget(lbl_meta); c_layout.addLayout(row_info); c_layout.addStretch()
        
        # Buttons
        h_btn = QHBoxLayout(); h_btn.setSpacing(8)
        
        btn_del = QPushButton(); btn_del.setIcon(qta.icon('fa5s.trash', color='#ef4565')); btn_del.setToolTip("حذف")
        btn_del.setFixedSize(34, 34); btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.setStyleSheet("background: #2b2b3d; border: 1px solid #3a3a4e; border-radius: 6px;")
        btn_del.clicked.connect(lambda: self.p_widget.delete_product_single(self.product.id))

        btn_dup = QPushButton(); btn_dup.setIcon(qta.icon('fa5s.copy', color='#a6accd')); btn_dup.setToolTip("کپی")
        btn_dup.setFixedSize(34, 34); btn_dup.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_dup.setStyleSheet("background: #2b2b3d; border: 1px solid #3a3a4e; border-radius: 6px;")
        btn_dup.clicked.connect(lambda: self.p_widget.duplicate_product(self.product.id))

        btn_edit = QPushButton("ویرایش"); btn_edit.setIcon(qta.icon('fa5s.pen', color='white'))
        btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_edit.setStyleSheet("background: #7f5af0; border: none; border-radius: 6px; color: white; padding: 0 10px; height: 34px; font-weight: bold; font-size: 12px;")
        btn_edit.clicked.connect(lambda: self.p_widget.open_editor_dialog(self.product.id))
        
        h_btn.addWidget(btn_del); h_btn.addWidget(btn_dup); h_btn.addWidget(btn_edit, 1)
        c_layout.addLayout(h_btn)
        
        layout.addWidget(content)

    def on_checked(self, state):
        self._selected = (state == 2)
        self.setStyleSheet(self.selected_style if self._selected else self.default_style)
        self.selectionChanged.emit(self.product.id, self._selected)


# ==============================================================================
# Main Manager Widget
# ==============================================================================
class ProductsWidget(QWidget):
    def __init__(self, bot_app=None):
        super().__init__()
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.bot_app = bot_app
        self.selected_ids = set()
        
        self.setup_ui()
        self._data_loaded = False

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 1. Header
        top_row = QHBoxLayout()
        lbl_title = QLabel("مدیریت محصولات")
        lbl_title.setStyleSheet("font-size: 24px; font-weight: 900; color: white;")
        
        # Bulk Actions
        self.bulk_toolbar = QFrame(); self.bulk_toolbar.setVisible(False)
        self.bulk_toolbar.setStyleSheet("background: #2b2b3d; border-radius: 8px; border: 1px solid #ef4565;")
        h_bulk = QHBoxLayout(self.bulk_toolbar); h_bulk.setContentsMargins(10, 5, 10, 5)
        
        self.lbl_sel_count = QLabel("0 انتخاب شده"); self.lbl_sel_count.setStyleSheet("color: white; font-weight: bold; margin-left: 10px;")
        btn_bulk_del = QPushButton("حذف گروهی"); btn_bulk_del.setIcon(qta.icon('fa5s.trash', color='#ef4565'))
        btn_bulk_del.setStyleSheet("background: transparent; border: 1px solid #ef4565; color: #ef4565; border-radius: 6px; padding: 6px 12px; font-weight: bold;")
        btn_bulk_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_bulk_del.clicked.connect(self.delete_bulk_slot)
        
        h_bulk.addWidget(self.lbl_sel_count); h_bulk.addWidget(btn_bulk_del); h_bulk.addStretch()
        
        top_row.addWidget(lbl_title)
        top_row.addWidget(self.bulk_toolbar)
        top_row.addStretch()
        
        btn_import = QPushButton("ورودی اکسل"); btn_import.setIcon(qta.icon('fa5s.file-import', color='white')); btn_import.setStyleSheet("background: #3da9fc; color: white; border-radius: 6px; padding: 8px;")
        btn_import.clicked.connect(self.import_data_slot)
        btn_export = QPushButton("خروجی اکسل"); btn_export.setIcon(qta.icon('fa5s.file-excel', color='white')); btn_export.setStyleSheet("background: #2cb67d; color: white; border-radius: 6px; padding: 8px;")
        btn_export.clicked.connect(self.export_data_slot)
        top_row.addWidget(btn_import); top_row.addWidget(btn_export)
        layout.addLayout(top_row)

        # 2. Search Box
        search_box = QFrame(); search_box.setStyleSheet("background: #21212e; border-radius: 12px; padding: 10px;")
        s_layout = QHBoxLayout(search_box)
        self.inp_search = QLineEdit(); self.inp_search.setPlaceholderText("🔍 نام، برند یا تگ محصول...")
        self.inp_search.setStyleSheet("background: #16161a; border: 1px solid #3a3a4e; padding: 10px; border-radius: 8px; color: white;")
        self.inp_search.returnPressed.connect(self.refresh_data_slot)
        
        self.cmb_cat_filter = QComboBox(); self.cmb_cat_filter.addItem("همه دسته‌ها", None)
        self.cmb_cat_filter.setStyleSheet("background: #16161a; color: white; padding: 8px; border-radius: 8px; min-width: 150px;")
        
        self.chk_stock = QCheckBox("فقط موجودها"); self.chk_stock.setStyleSheet("color: white;")
        
        btn_search = QPushButton("جستجو"); btn_search.setIcon(qta.icon('fa5s.search', color='white')); btn_search.clicked.connect(self.refresh_data_slot)
        btn_search.setStyleSheet("background: #7f5af0; color: white; border-radius: 8px; padding: 10px 20px; font-weight: bold;")
        
        btn_add = QPushButton(" محصول جدید"); btn_add.setIcon(qta.icon('fa5s.plus', color='white'))
        btn_add.clicked.connect(lambda: self.open_editor_dialog(None))
        btn_add.setStyleSheet("background: #2cb67d; color: white; border-radius: 8px; padding: 10px 20px; font-weight: bold;")
        
        s_layout.addWidget(self.inp_search, 2)
        s_layout.addWidget(self.cmb_cat_filter, 1)
        s_layout.addWidget(self.chk_stock)
        s_layout.addWidget(btn_search)
        s_layout.addWidget(btn_add)
        layout.addWidget(search_box)

        # 3. Grid
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setStyleSheet("background: transparent; border: none;")
        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(20)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(self.grid_container)
        layout.addWidget(scroll)
        
    def showEvent(self, event):  # <-- این متد را به کلاس اضافه کنید
        super().showEvent(event)
        if not self._data_loaded:
            QTimer.singleShot(100, self.refresh_data) # یا refresh_data_slot
            self._data_loaded = True    

    # --- Logic ---
    def open_editor_dialog(self, pid):
        """باز کردن دیالوگ ویرایش/افزودن"""
        dialog = ProductEditorDialog(self, pid)
        # اتصال سیگنال ذخیره موفق به رفرش لیست
        dialog.product_saved.connect(self.refresh_data_slot)
        dialog.exec()

    @asyncSlot()
    async def refresh_data_slot(self):
        await self.refresh_data()

    async def refresh_data(self):
        # پاکسازی گرید
        for i in reversed(range(self.grid_layout.count())): 
            if self.grid_layout.itemAt(i).widget(): 
                self.grid_layout.itemAt(i).widget().setParent(None)
        
        self.selected_ids.clear(); self.update_bulk_toolbar()
        
        loop = asyncio.get_running_loop()
        try:
            def fetch():
                with next(get_db()) as db:
                    cats = crud.get_all_categories(db)
                    prods = crud.advanced_search_products(
                        db, query=self.inp_search.text(),
                        category_id=self.cmb_cat_filter.currentData(),
                        in_stock_only=self.chk_stock.isChecked()
                    )
                    return cats, prods

            cats, prods = await loop.run_in_executor(None, fetch)
            
            # آپدیت فیلتر دسته‌بندی
            current_cat = self.cmb_cat_filter.currentData()
            self.cmb_cat_filter.clear(); self.cmb_cat_filter.addItem("همه دسته‌ها", None)
            for c in cats:
                self.cmb_cat_filter.addItem(c.name, c.id)
            if current_cat:
                idx = self.cmb_cat_filter.findData(current_cat)
                if idx >= 0: self.cmb_cat_filter.setCurrentIndex(idx)
            
            # رندر کارت‌ها (تعداد ستون‌ها بر اساس عرض صفحه)
            cols = max(1, self.grid_container.width() // 280)
            for i, p in enumerate(prods):
                card = ProductCard(p, self)
                card.selectionChanged.connect(self.on_card_selection)
                self.grid_layout.addWidget(card, i // cols, i % cols)
                
        except Exception as e:
            logger.error(f"Refresh error: {e}")

    def on_card_selection(self, pid, selected):
        if selected: self.selected_ids.add(pid)
        else: self.selected_ids.discard(pid)
        self.update_bulk_toolbar()

    def update_bulk_toolbar(self):
        count = len(self.selected_ids)
        self.bulk_toolbar.setVisible(count > 0)
        self.lbl_sel_count.setText(f"{count} انتخاب شده")

    @asyncSlot()
    async def delete_product_single(self, pid):
        if QMessageBox.question(self, "حذف محصول", "آیا مطمئن هستید؟ این عملیات غیرقابل بازگشت است.") == QMessageBox.StandardButton.Yes:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: crud.delete_product(next(get_db()), pid))
            await self.refresh_data()

    @asyncSlot()
    async def duplicate_product(self, pid):
        loop = asyncio.get_running_loop()
        try:
            def dup_op():
                with next(get_db()) as db:
                    p = crud.get_product(db, pid)
                    if not p: return
                    data = {c.name: getattr(p, c.name) for c in p.__table__.columns if c.name not in ['id', 'created_at', 'updated_at']}
                    data['name'] += " (کپی)"
                    vars_data = [{"name": v.name, "price_adjustment": v.price_adjustment, "stock": v.stock} for v in p.variants]
                    crud.create_product_with_variants(db, data, vars_data)
            await loop.run_in_executor(None, dup_op)
            await self.refresh_data()
            if hasattr(self.window(), 'show_toast'): self.window().show_toast("محصول کپی شد.")
        except Exception as e: logger.error(e)

    @asyncSlot()
    async def delete_bulk_slot(self):
        if QMessageBox.question(self, "حذف گروهی", f"آیا از حذف {len(self.selected_ids)} محصول اطمینان دارید؟") == QMessageBox.StandardButton.Yes:
            ids = list(self.selected_ids)
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: crud.bulk_delete_products(next(get_db()), ids))
            await self.refresh_data()

    # --- Import / Export ---
    def export_data_slot(self):
        path, _ = QFileDialog.getSaveFileName(self, "ذخیره فایل اکسل", "products_export.xlsx", "Excel Files (*.xlsx)")
        if not path: return
        self.sender().setEnabled(False) # غیرفعال کردن دکمه
        asyncio.create_task(self._perform_export(path))

    async def _perform_export(self, path):
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: self._do_export_logic(path))
            QTimer.singleShot(0, lambda: QMessageBox.information(self, "موفق", "فایل اکسل ذخیره شد."))
        except Exception as e:
            QTimer.singleShot(0, lambda: QMessageBox.critical(self, "خطا", str(e)))
        finally:
            # پیدا کردن دکمه اکسپورت و فعال‌سازی مجدد
            # (چون sender در اینجا ممکن است در دسترس نباشد، بهتر است رفرنس دکمه را داشته باشیم یا بیخیال شویم)
            pass 

    def _do_export_logic(self, path):
        with next(get_db()) as db:
            prods = crud.get_all_products_raw(db)
            data = []
            for p in prods:
                data.append({
                    "شناسه": p.id,
                    "نام محصول": p.name,
                    "قیمت": p.price,
                    "موجودی": p.stock,
                    "دسته‌بندی": p.category.name if p.category else ""
                })
            df = pd.DataFrame(data)
            df.to_excel(path, index=False)

    def import_data_slot(self):
        path, _ = QFileDialog.getOpenFileName(self, "انتخاب فایل اکسل", "", "Excel Files (*.xlsx *.xls)")
        if not path: return
        self.sender().setEnabled(False)
        asyncio.create_task(self._perform_import(path))

    async def _perform_import(self, path):
        try:
            loop = asyncio.get_running_loop()
            s, f = await loop.run_in_executor(None, lambda: self._do_import_logic(path))
            QTimer.singleShot(0, lambda: QMessageBox.information(self, "پایان", f"موفق: {s}\nناموفق: {f}"))
            await self.refresh_data()
        except Exception as e:
            QTimer.singleShot(0, lambda: QMessageBox.critical(self, "خطا", str(e)))

    def _do_import_logic(self, path):
        df = pd.read_excel(path)
        df = df.fillna("")
        success, fail = 0, 0
        with next(get_db()) as db:
            for _, row in df.iterrows():
                try:
                    data = {
                        "name": str(row.get("نام محصول", "New Product")),
                        "price": float(row.get("قیمت", 0)),
                        "stock": int(row.get("موجودی", 0))
                    }
                    crud.create_product_with_variants(db, data, [])
                    success += 1
                except: fail += 1
        return success, fail