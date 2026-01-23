from sqlalchemy import (
    Column, Integer, String, Boolean, ForeignKey,
    DateTime, Numeric, Text, Index
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

# ==============================================================================
# 1. مدل کاربر (User Model)
# ==============================================================================
class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, autoincrement=False, comment="آیدی عددی تلگرام")
    full_name = Column(String(255), nullable=True)
    username = Column(String(255), nullable=True)
    phone_number = Column(String(20), nullable=True)
    
    # سطح دسترسی و وضعیت
    is_admin = Column(Boolean, default=False, nullable=False)
    is_banned = Column(Boolean, default=False, nullable=False)

    # اطلاعات تکمیلی کاربر (برای راحتی در خرید بعدی)
    saved_address = Column(Text, nullable=True)
    saved_phone = Column(String(20), nullable=True)
    
    # فیلدهای سیستمی
    private_note = Column(Text, nullable=True, comment="یادداشت محرمانه ادمین")
    last_seen = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # روابط (Relationships)
    # استفاده از lazy="selectin" برای لود سریع و بهینه در کوئری‌های Async/Sync
    orders = relationship("Order", back_populates="user", cascade="all, delete-orphan", lazy="selectin")
    cart_items = relationship("CartItem", back_populates="user", cascade="all, delete-orphan", lazy="selectin")
    addresses = relationship("UserAddress", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("ProductNotification", back_populates="user", cascade="all, delete-orphan")

    # ایندکس برای سرعت فیلترینگ
    __table_args__ = (
        Index("idx_user_banned", "is_banned"),
        Index("idx_user_created", "created_at"),
    )

    def __repr__(self):
        return f"<User(id={self.user_id}, name={self.full_name})>"


# ==============================================================================
# 2. مدل دسته‌بندی (Category Model)
# ==============================================================================
class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    parent_id = Column(Integer, ForeignKey("categories.id", ondelete="CASCADE"), nullable=True)

    # رابطه بازگشتی (Self-Referential) برای زیردسته‌ها
    parent = relationship("Category", remote_side=[id], back_populates="children")
    children = relationship("Category", back_populates="parent", cascade="all, delete-orphan")
    
    products = relationship("Product", back_populates="category", cascade="all, delete-orphan", lazy="selectin")


# ==============================================================================
# 3. مدل محصول و متغیرها (Product & Variants)
# ==============================================================================
class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    brand = Column(String(100), nullable=True, index=True)
    
    # اطلاعات مالی و موجودی
    price = Column(Numeric(12, 0), nullable=False)
    discount_price = Column(Numeric(12, 0), nullable=True)
    stock = Column(Integer, default=0, nullable=False)
    
    # مدیا
    image_path = Column(String(512), nullable=True)
    image_file_id = Column(String(255), nullable=True, comment="FileID تلگرام برای سرعت ارسال")
    
    # ویژگی‌ها
    is_top_seller = Column(Boolean, default=False, nullable=False)
    tags = Column(Text, nullable=True, comment="کلمات کلیدی جدا شده با کاما")
    related_product_ids = Column(String(255), nullable=True, comment="ID محصولات پیشنهادی")

    # متادیتا
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # روابط
    category = relationship("Category", back_populates="products", lazy="joined")
    variants = relationship("ProductVariant", back_populates="product", cascade="all, delete-orphan", lazy="selectin")
    
    cart_items = relationship("CartItem", back_populates="product", cascade="all, delete-orphan")
    order_items = relationship("OrderItem", back_populates="product")
    favorited_by = relationship("Favorite", back_populates="product", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_product_cat", "category_id"),
        Index("idx_product_stock", "stock"),
    )

class ProductVariant(Base):
    """مدل جدید: متغیرهای محصول (رنگ، سایز و...) برای مدیریت موجودی دقیق"""
    __tablename__ = "product_variants"
    
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    
    name = Column(String(100), nullable=False) # مثال: "قرمز - XL"
    price_adjustment = Column(Numeric(12, 0), default=0) # تفاوت قیمت نسبت به محصول اصلی
    stock = Column(Integer, default=0)
    
    product = relationship("Product", back_populates="variants")


# ==============================================================================
# 4. مدل سبد خرید و سفارشات (Cart & Order Models)
# ==============================================================================
class CartItem(Base):
    __tablename__ = "cart_items"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False)
    # اگر از سیستم واریانت استفاده کردید، این فیلد پر می‌شود
    variant_id = Column(Integer, ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True)
    
    quantity = Column(Integer, default=1, nullable=False)
    selected_attributes = Column(Text, nullable=True) # برای سازگاری با سیستم قدیمی (متن ساده)
    
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="cart_items")
    product = relationship("Product", back_populates="cart_items", lazy="joined")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    
    # وضعیت سفارش: pending_payment, approved, shipped, rejected, paid, cancelled
    status = Column(String(32), default="pending_payment", nullable=False, index=True) 
    
    total_amount = Column(Numeric(12, 0), nullable=False)
    shipping_cost = Column(Numeric(12, 0), default=0)
    
    shipping_address = Column(Text, nullable=False)
    postal_code = Column(String(20), nullable=True)
    phone_number = Column(String(20), nullable=True)
    
    payment_receipt_photo_id = Column(String(255), nullable=True)
    tracking_code = Column(String(100), nullable=True) # کد رهگیری پستی
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="orders", lazy="joined")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan", lazy="selectin")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    variant_id = Column(Integer, ForeignKey("product_variants.id", ondelete="SET NULL"), nullable=True)
    
    quantity = Column(Integer, nullable=False)
    price_at_purchase = Column(Numeric(12, 0), nullable=False) # قیمت در لحظه خرید (مهم برای تاریخچه)
    selected_attributes = Column(Text, nullable=True)

    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items", lazy="joined")


# ==============================================================================
# 5. امکانات جانبی (Favorites, Notifications, Settings, Address)
# ==============================================================================
class Favorite(Base):
    __tablename__ = "favorites"
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    product = relationship("Product", back_populates="favorited_by")


class ProductNotification(Base):
    """خبرم کن وقتی موجود شد"""
    __tablename__ = "product_notifications"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user = relationship("User", back_populates="notifications")


class UserAddress(Base):
    __tablename__ = "user_addresses"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    title = Column(String(50), nullable=False) # خانه، محل کار
    address_text = Column(Text, nullable=False)
    postal_code = Column(String(20), nullable=True)
    user = relationship("User", back_populates="addresses")


class Setting(Base):
    __tablename__ = "settings"
    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=True)
    description = Column(String(255), nullable=True)