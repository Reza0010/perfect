import asyncio
from typing import List, Tuple, Optional, Dict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QMessageBox,
    QTreeWidget, QTreeWidgetItem, QLineEdit, QLabel, QFrame, 
    QSplitter, QComboBox, QSizePolicy, QGraphicsDropShadowEffect
)
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtCore import Qt, QSize, QTimer
from qasync import asyncSlot
import qtawesome as qta

# Import Data Layer
from db import crud
from db.database import get_db

# --- ثوابت استایل ---
BG_COLOR = "#16161a"
PANEL_BG = "#242629"
ACCENT_COLOR = "#7f5af0"
TEXT_COLOR = "#fffffe"
HINT_COLOR = "#94a1b2"

class CategoriesWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.selected_cat_id: Optional[int] = None
        self.all_categories_cache = [] 
        
        self.setup_ui()
        
        # فلگ برای جلوگیری از رفرش تکراری
        self._data_loaded = False

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # تقسیم‌کننده صفحه
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet(f"""
            QSplitter::handle {{ 
                background-color: {HINT_COLOR}; 
                margin: 20px 0px;
            }}
        """)

        # --- بخش ۱: لیست درختی (سمت راست) ---
        tree_container = QFrame()
        tree_container.setStyleSheet(f"background-color: {PANEL_BG}; border-radius: 16px; border: 1px solid {BG_COLOR};")
        tree_layout = QVBoxLayout(tree_container)
        tree_layout.setContentsMargins(15, 20, 15, 15)
        tree_layout.setSpacing(10)
        
        # هدر لیست
        header_layout = QHBoxLayout()
        lbl_list = QLabel("📂 ساختار دسته‌بندی‌ها")
        lbl_list.setStyleSheet(f"color: {TEXT_COLOR}; font-weight: 900; font-size: 16px;")
        
        btn_refresh = QPushButton()
        btn_refresh.setIcon(qta.icon('fa5s.sync-alt', color=HINT_COLOR))
        btn_refresh.setFixedSize(32, 32)
        btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_refresh.setToolTip("بروزرسانی لیست")
        btn_refresh.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: 1px solid {BG_COLOR}; border-radius: 8px; }}
            QPushButton:hover {{ background: rgba(255,255,255,0.05); border-color: {ACCENT_COLOR}; }}
        """)
        btn_refresh.clicked.connect(self.refresh_data)
        
        header_layout.addWidget(lbl_list)
        header_layout.addStretch()
        header_layout.addWidget(btn_refresh)
        tree_layout.addLayout(header_layout)

        # خط جداکننده
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {BG_COLOR};")
        tree_layout.addWidget(line)

        # ویجت درخت
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.tree.setIndentation(25)
        self.tree.setAnimated(True)
        self.tree.itemClicked.connect(self.on_item_clicked)
        self.tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: transparent;
                border: none;
                color: {TEXT_COLOR};
                font-size: 14px;
                outline: none;
            }}
            QTreeWidget::item {{
                padding: 8px;
                border-radius: 6px;
                margin-bottom: 4px;
                border: 1px solid transparent;
            }}
            QTreeWidget::item:hover {{
                background-color: {BG_COLOR};
                border: 1px solid rgba(127, 90, 240, 0.3);
            }}
            QTreeWidget::item:selected {{
                background-color: rgba(127, 90, 240, 0.15);
                color: white;
                border: 1px solid {ACCENT_COLOR};
            }}
        """)
        tree_layout.addWidget(self.tree)
        
        # دکمه شناور افزودن جدید
        self.btn_new = QPushButton("  دسته جدید")
        self.btn_new.setIcon(qta.icon('fa5s.plus', color='white'))
        self.btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new.setFixedHeight(45)
        self.btn_new.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT_COLOR};
                color: white; border-radius: 10px; font-weight: bold; border: none;
                text-align: center;
            }}
            QPushButton:hover {{ background: #6f4ce0; }}
            QPushButton:pressed {{ padding-top: 3px; }}
        """)
        self.btn_new.clicked.connect(self.reset_form)
        tree_layout.addWidget(self.btn_new)

        # --- بخش ۲: فرم عملیات (سمت چپ) ---
        self.form_container = QFrame()
        self.form_container.setFixedWidth(360) 
        
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(25); shadow.setColor(QColor(0,0,0,80)); shadow.setOffset(0,5)
        self.form_container.setGraphicsEffect(shadow)

        self.form_container.setStyleSheet(f"""
            QFrame {{
                background-color: {PANEL_BG};
                border-radius: 16px;
                border: 1px solid {BG_COLOR};
            }}
            QLabel {{ color: {HINT_COLOR}; font-size: 13px; border: none; background: transparent; margin-top: 5px; }}
            QLineEdit, QComboBox {{
                background-color: {BG_COLOR};
                border: 1px solid #3a3a4e;
                border-radius: 8px;
                padding: 12px;
                color: white;
                font-size: 13px;
            }}
            QLineEdit:focus, QComboBox:focus {{ border: 1px solid {ACCENT_COLOR}; }}
            QComboBox::drop-down {{ border: none; }}
        """)
        
        form_layout = QVBoxLayout(self.form_container)
        form_layout.setContentsMargins(25, 30, 25, 30)
        form_layout.setSpacing(10)

        # آیکون دایره‌ای بالای فرم
        self.lbl_icon = QLabel()
        self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_icon.setFixedSize(80, 80)
        self.lbl_icon.setStyleSheet(f"background-color: {ACCENT_COLOR}20; border-radius: 40px; margin-bottom: 10px;")
        self.lbl_icon.setPixmap(qta.icon('fa5s.layer-group', color=ACCENT_COLOR).pixmap(QSize(40, 40)))
        
        icon_layout = QHBoxLayout()
        icon_layout.addStretch(); icon_layout.addWidget(self.lbl_icon); icon_layout.addStretch()
        form_layout.addLayout(icon_layout)

        # عنوان فرم
        self.lbl_form_title = QLabel("افزودن دسته جدید")
        self.lbl_form_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_form_title.setStyleSheet("color: white; font-size: 18px; font-weight: bold; margin-bottom: 15px;")
        form_layout.addWidget(self.lbl_form_title)

        # فیلدها
        form_layout.addWidget(QLabel("نام دسته‌بندی:"))
        self.inp_name = QLineEdit()
        self.inp_name.setPlaceholderText("مثلاً: کیف و کفش")
        self.inp_name.setClearButtonEnabled(True)
        form_layout.addWidget(self.inp_name)

        form_layout.addWidget(QLabel("دسته والد:"))
        self.inp_parent = QComboBox()
        self.inp_parent.setCursor(Qt.CursorShape.PointingHandCursor)
        form_layout.addWidget(self.inp_parent)

        form_layout.addStretch()

        # دکمه‌ها
        self.btn_save = QPushButton("ذخیره تغییرات")
        self.btn_save.setIcon(qta.icon('fa5s.save', color='white'))
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setFixedHeight(45)
        self.btn_save.setStyleSheet("""
            QPushButton { background-color: #2cb67d; color: white; border-radius: 8px; font-weight: bold; border: none; }
            QPushButton:hover { background-color: #27ae60; }
        """)
        self.btn_save.clicked.connect(self.save_category)
        form_layout.addWidget(self.btn_save)

        self.btn_delete = QPushButton("حذف دسته")
        self.btn_delete.setIcon(qta.icon('fa5s.trash-alt', color='white'))
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.setFixedHeight(45)
        self.btn_delete.setStyleSheet("""
            QPushButton { background-color: #ef4565; color: white; border-radius: 8px; font-weight: bold; border: none; }
            QPushButton:hover { background-color: #d03e58; }
        """)
        self.btn_delete.clicked.connect(self.delete_category)
        self.btn_delete.hide()
        form_layout.addWidget(self.btn_delete)

        splitter.addWidget(tree_container)
        splitter.addWidget(self.form_container)
        splitter.setStretchFactor(0, 1)

        main_layout.addWidget(splitter)

    # --- FIX: اضافه کردن showEvent برای لود امن دیتا ---
    def showEvent(self, event):
        super().showEvent(event)
        if not self._data_loaded:
            # تاخیر کوچک برای اطمینان از اینکه UI رندر شده است
            QTimer.singleShot(100, self.refresh_data)
            self._data_loaded = True

    @asyncSlot()
    async def refresh_data(self):
        """بارگذاری داده‌ها با هندل کردن خطاها"""
        self.tree.clear()
        
        loop = asyncio.get_running_loop()
        try:
            def fetch():
                with next(get_db()) as db:
                    if hasattr(crud, 'get_categories_with_counts'):
                        return crud.get_categories_with_counts(db)
                    else:
                        cats = crud.get_all_categories(db)
                        return [(c, 0) for c in cats]
            
            data = await loop.run_in_executor(None, fetch)
            self.all_categories_cache = [(cat.id, cat.name, cat.parent_id) for cat, _ in data]
            self._populate_parent_combo()

            items_map = {}
            for cat, count in data:
                text = cat.name
                item = QTreeWidgetItem([text])
                item.setData(0, Qt.ItemDataRole.UserRole, cat.id)       
                item.setData(0, Qt.ItemDataRole.UserRole + 1, cat.parent_id)
                item.setData(0, Qt.ItemDataRole.UserRole + 2, count)    
                
                if count > 0:
                    item.setText(0, f"{cat.name}   [ {count} کالا ]")
                    icon = qta.icon('fa5s.folder', color='#f72585')
                else:
                    item.setText(0, f"{cat.name}")
                    icon = qta.icon('fa5s.folder', color=HINT_COLOR)
                
                item.setIcon(0, icon)
                items_map[cat.id] = {"item": item, "pid": cat.parent_id}

            for cid, info in items_map.items():
                item = info["item"]
                pid = info["pid"]
                if pid and pid in items_map:
                    items_map[pid]["item"].addChild(item)
                    items_map[pid]["item"].setExpanded(True)
                else:
                    self.tree.addTopLevelItem(item)

        except Exception as e:
            print(f"Categories Error: {e}")

    def _populate_parent_combo(self, exclude_id=None):
        self.inp_parent.blockSignals(True)
        self.inp_parent.clear()
        self.inp_parent.addItem("--- دسته اصلی ---", None)
        
        for cid, name, pid in self.all_categories_cache:
            if exclude_id and cid == exclude_id:
                continue
            self.inp_parent.addItem(name, cid)
            
        self.inp_parent.blockSignals(False)

    def on_item_clicked(self, item, col):
        cid = item.data(0, Qt.ItemDataRole.UserRole)
        pid = item.data(0, Qt.ItemDataRole.UserRole + 1)
        count = item.data(0, Qt.ItemDataRole.UserRole + 2)
        
        raw_text = item.text(0)
        clean_name = raw_text.split("   [")[0].strip()
        
        self.selected_cat_id = cid
        self.inp_name.setText(clean_name)
        self._populate_parent_combo(exclude_id=cid)
        
        idx = self.inp_parent.findData(pid)
        self.inp_parent.setCurrentIndex(max(0, idx))

        self.lbl_form_title.setText(f"ویرایش: {clean_name}")
        self.lbl_icon.setStyleSheet(f"background-color: #f39c1220; border: 2px solid #f39c12; border-radius: 40px;")
        self.lbl_icon.setPixmap(qta.icon('fa5s.edit', color='#f39c12').pixmap(40,40))
        
        self.btn_save.setText("بروزرسانی")
        self.btn_save.setStyleSheet("""
            QPushButton { background-color: #f39c12; color: white; border-radius: 8px; font-weight: bold; border: none; }
            QPushButton:hover { background-color: #e67e22; }
        """)
        
        if count == 0: self.btn_delete.show()
        else: self.btn_delete.hide()

    def reset_form(self):
        self.selected_cat_id = None
        self.tree.clearSelection()
        self.inp_name.clear()
        self._populate_parent_combo()
        
        self.lbl_form_title.setText("افزودن دسته جدید")
        self.lbl_icon.setStyleSheet(f"background-color: {ACCENT_COLOR}20; border-radius: 40px;")
        self.lbl_icon.setPixmap(qta.icon('fa5s.layer-group', color=ACCENT_COLOR).pixmap(40,40))
        
        self.btn_save.setText("ایجاد دسته‌بندی")
        self.btn_save.setStyleSheet("""
            QPushButton { background-color: #2cb67d; color: white; border-radius: 8px; font-weight: bold; border: none; }
            QPushButton:hover { background-color: #27ae60; }
        """)
        self.btn_delete.hide()
        self.inp_name.setFocus()

    @asyncSlot()
    async def save_category(self):
        name = self.inp_name.text().strip()
        pid = self.inp_parent.currentData()
        
        if not name: return

        loop = asyncio.get_running_loop()
        try:
            def db_op():
                with next(get_db()) as db:
                    if self.selected_cat_id:
                        return crud.update_category(db, self.selected_cat_id, name, pid)
                    else:
                        return crud.create_category(db, name, pid)
            
            await loop.run_in_executor(None, db_op)
            self.reset_form()
            await self.refresh_data()
            if hasattr(self.window(), 'show_toast'):
                self.window().show_toast("تغییرات ذخیره شد.")

        except Exception as e:
            QMessageBox.critical(self, "خطا", f"مشکلی پیش آمد:\n{e}")

    @asyncSlot()
    async def delete_category(self):
        if not self.selected_cat_id: return
        
        if QMessageBox.question(self, "تایید حذف", "آیا مطمئن هستید؟", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            try:
                loop = asyncio.get_running_loop()
                # اگر متد safe وجود نداشت، از متد معمولی استفاده کن
                if hasattr(crud, 'delete_category_safe'):
                    func = crud.delete_category_safe
                else:
                    def func(cid): 
                        with next(get_db()) as db: crud.delete_category(db, cid)
                
                await loop.run_in_executor(None, lambda: func(self.selected_cat_id))
                self.reset_form()
                await self.refresh_data()
                if hasattr(self.window(), 'show_toast'):
                    self.window().show_toast("دسته حذف شد.", is_error=True)
            except Exception as e:
                print(e)