import logging
from typing import List, Optional, Tuple, Any, Dict, Union
from datetime import datetime, timedelta

from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import or_, desc, asc, func, and_, case
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from . import models
from config import ADMIN_USER_IDS

logger = logging.getLogger(__name__)

# ======================================================================
# 1. مدیریت کاربران (User Management)
# ======================================================================

def get_user_by_telegram_id(db: Session, telegram_id: int) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.user_id == telegram_id).first()

def get_or_create_user(db: Session, telegram_id: int, full_name: str, username: str = None) -> models.User:
    """ایجاد یا آپدیت کاربر با مدیریت خطا و همگام‌سازی"""
    try:
        user = get_user_by_telegram_id(db, telegram_id)
        is_admin = telegram_id in ADMIN_USER_IDS

        if not user:
            user = models.User(
                user_id=telegram_id,
                full_name=full_name,
                username=username,
                is_admin=is_admin,
                created_at=datetime.now()
            )
            db.add(user)
        else:
            # فقط در صورت تغییر آپدیت کن
            if user.full_name != full_name: user.full_name = full_name
            if user.username != username: user.username = username
            if user.is_admin != is_admin: user.is_admin = is_admin
            
            user.updated_at = datetime.now()
            user.last_seen = datetime.now()
        
        db.commit()
        db.refresh(user)
        return user
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to get_or_create_user {telegram_id}: {e}")
        raise

def get_all_users(db: Session, skip: int = 0, limit: int = 10000) -> List[models.User]:
    """دریافت کاربران به همراه سفارشات (selectinload برای پرفورمنس بالا)"""
    return (
        db.query(models.User)
        .options(selectinload(models.User.orders)) 
        .order_by(desc(models.User.last_seen)) # مرتب‌سازی بر اساس آخرین بازدید
        .offset(skip)
        .limit(limit)
        .all()
    )

def update_user_info(db: Session, user_id: int, **kwargs) -> bool:
    """آپدیت عمومی اطلاعات کاربر"""
    try:
        user = get_user_by_telegram_id(db, user_id)
        if user:
            for key, value in kwargs.items():
                if hasattr(user, key):
                    setattr(user, key, value)
            db.commit()
            return True
        return False
    except SQLAlchemyError:
        db.rollback()
        return False

def get_user_stats(db: Session, user_id: int) -> Dict:
    """محاسبه آمار کاربر به صورت بهینه (SQL-side calculation)"""
    try:
        # محاسبه مجموع خرید موفق با کوئری مستقیم (سریع‌تر از پایتون)
        total_spent = db.query(func.coalesce(func.sum(models.Order.total_amount), 0)).filter(
            models.Order.user_id == user_id,
            models.Order.status.in_(['approved', 'shipped', 'paid'])
        ).scalar()
        
        total_orders = db.query(func.count(models.Order.id)).filter_by(user_id=user_id).scalar()
        
        user = get_user_by_telegram_id(db, user_id)
        if not user: return {}

        return {
            "join_date": user.created_at,
            "total_orders": total_orders,
            "total_spent": float(total_spent),
            "last_seen": user.last_seen or user.updated_at
        }
    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        return {}

def get_total_user_count(db: Session) -> int:
    return db.query(func.count(models.User.user_id)).scalar()

# ======================================================================
# 2. مدیریت دسته‌بندی‌ها
# ======================================================================

def get_all_categories(db: Session) -> List[models.Category]:
    return db.query(models.Category).order_by(models.Category.id).all()

def get_categories_with_counts(db: Session) -> List[Tuple[models.Category, int]]:
    """دریافت دسته‌ها + تعداد محصول فعال (Left Join)"""
    return (
        db.query(models.Category, func.count(models.Product.id))
        .outerjoin(models.Product)
        .group_by(models.Category.id)
        .order_by(models.Category.id)
        .all()
    )

def create_category(db: Session, name: str, parent_id: Optional[int] = None) -> models.Category:
    try:
        cat = models.Category(name=name.strip(), parent_id=parent_id)
        db.add(cat)
        db.commit()
        db.refresh(cat)
        return cat
    except SQLAlchemyError:
        db.rollback()
        raise

def update_category(db: Session, cat_id: int, name: str, parent_id: Optional[int] = None) -> Optional[models.Category]:
    try:
        cat = db.query(models.Category).filter_by(id=cat_id).first()
        if cat:
            cat.name = name.strip()
            cat.parent_id = parent_id
            db.commit()
            db.refresh(cat)
        return cat
    except SQLAlchemyError:
        db.rollback()
        raise

def delete_category(db: Session, cat_id: int) -> bool:
    try:
        cat = db.query(models.Category).filter_by(id=cat_id).first()
        if cat:
            # بروزرسانی محصولاتی که در این دسته بودند (Null کردن دسته)
            db.query(models.Product).filter_by(category_id=cat_id).update({models.Product.category_id: None})
            db.delete(cat)
            db.commit()
            return True
        return False
    except SQLAlchemyError:
        db.rollback()
        raise

def delete_category_safe(cat_id: int):
    """رپر ایمن برای حذف (بدون نیاز به پاس دادن سشن از بیرون) - برای استفاده در تردها"""
    # نکته: چون اینجا سشن جدید می‌سازیم، نباید در ترنزکشن‌های پیچیده تو در تو استفاده شود
    # اما برای حذف تکی در UI عالی است.
    # پیاده‌سازی این تابع وابسته به نحوه استفاده در categories_widget است.
    pass 

# ======================================================================
# 3. مدیریت محصولات
# ======================================================================

def get_product(db: Session, prod_id: int) -> Optional[models.Product]:
    return db.query(models.Product).options(
        joinedload(models.Product.category),
        selectinload(models.Product.variants)
    ).filter_by(id=prod_id).first()

def get_all_products_raw(db: Session) -> List[models.Product]:
    return db.query(models.Product).options(joinedload(models.Product.category)).order_by(desc(models.Product.created_at)).all()

def advanced_search_products(
    db: Session, 
    query: str = "", 
    category_id: int = None,
    min_price: int = 0,
    max_price: int = 0,
    in_stock_only: bool = False,
    tag: str = ""
) -> List[models.Product]:
    """جستجوی پیشرفته و بهینه"""
    q = db.query(models.Product).options(joinedload(models.Product.category))
    
    if query:
        search_term = f"%{query}%"
        q = q.filter(
            or_(
                models.Product.name.ilike(search_term),
                models.Product.brand.ilike(search_term),
                models.Product.tags.ilike(search_term)
            )
        )
    
    if category_id:
        q = q.filter(models.Product.category_id == category_id)
        
    if min_price > 0:
        q = q.filter(models.Product.price >= min_price)
        
    if max_price > 0:
        q = q.filter(models.Product.price <= max_price)
        
    if in_stock_only:
        q = q.filter(models.Product.stock > 0)
        
    if tag:
        q = q.filter(models.Product.tags.ilike(f"%{tag}%"))
        
    return q.order_by(desc(models.Product.created_at)).all()

def create_product_with_variants(db: Session, product_data: dict, variants_data: List[dict]) -> models.Product:
    """ایجاد اتمیک محصول + متغیرها"""
    try:
        # 1. Product
        valid_cols = {c.key for c in models.Product.__table__.columns}
        clean_prod_data = {k: v for k, v in product_data.items() if k in valid_cols}
        
        prod = models.Product(**clean_prod_data)
        db.add(prod)
        db.flush() # دریافت ID قبل از کامیت
        
        # 2. Variants
        if variants_data:
            for v in variants_data:
                # حذف کلیدهای اضافی احتمالی
                v_clean = {k: v[k] for k in ["name", "price_adjustment", "stock"] if k in v}
                variant = models.ProductVariant(product_id=prod.id, **v_clean)
                db.add(variant)
            
        db.commit()
        db.refresh(prod)
        return prod
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error creating product: {e}")
        raise

def update_product_with_variants(db: Session, prod_id: int, product_data: dict, variants_data: List[dict]) -> models.Product:
    try:
        prod = db.query(models.Product).filter_by(id=prod_id).first()
        if not prod: raise ValueError(f"Product {prod_id} not found")
            
        # Update Fields
        valid_cols = {c.key for c in models.Product.__table__.columns}
        for k, v in product_data.items():
            if k in valid_cols:
                setattr(prod, k, v)
        
        prod.updated_at = datetime.now()
        
        # Update Variants (Delete all & Recreate strategy is simpler and safer here)
        if variants_data is not None:
            db.query(models.ProductVariant).filter_by(product_id=prod_id).delete()
            for v in variants_data:
                v_clean = {k: v[k] for k in ["name", "price_adjustment", "stock"] if k in v}
                variant = models.ProductVariant(product_id=prod_id, **v_clean)
                db.add(variant)
            
        db.commit()
        db.refresh(prod)
        
        # Stock Notification Check
        if prod.stock > 0:
            process_stock_notifications(db, prod_id)
            
        return prod
    except SQLAlchemyError:
        db.rollback()
        raise

def bulk_delete_products(db: Session, product_ids: List[int]) -> bool:
    try:
        # حذف وابستگی‌ها (Cascade manual if DB doesn't support it)
        db.query(models.CartItem).filter(models.CartItem.product_id.in_(product_ids)).delete(synchronize_session=False)
        db.query(models.Favorite).filter(models.Favorite.product_id.in_(product_ids)).delete(synchronize_session=False)
        db.query(models.ProductNotification).filter(models.ProductNotification.product_id.in_(product_ids)).delete(synchronize_session=False)
        db.query(models.ProductVariant).filter(models.ProductVariant.product_id.in_(product_ids)).delete(synchronize_session=False)
        
        # حذف محصولات
        db.query(models.Product).filter(models.Product.id.in_(product_ids)).delete(synchronize_session=False)
        db.commit()
        return True
    except SQLAlchemyError:
        db.rollback()
        raise

def delete_product(db: Session, prod_id: int) -> bool:
    return bulk_delete_products(db, [prod_id])

def bulk_update_products(db: Session, product_ids: List[int], updates: dict):
    try:
        db.query(models.Product).filter(models.Product.id.in_(product_ids)).update(updates, synchronize_session=False)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

def get_total_product_count(db: Session) -> int:
    return db.query(func.count(models.Product.id)).scalar()

def get_low_stock_products(db: Session, limit: int = 5) -> List[models.Product]:
    return db.query(models.Product).filter(
        models.Product.stock > 0,
        models.Product.stock <= 5
    ).limit(limit).all()

# ======================================================================
# 4. سبد خرید
# ======================================================================

def get_cart_items(db: Session, user_id: int) -> List[models.CartItem]:
    return db.query(models.CartItem).filter_by(user_id=user_id).options(joinedload(models.CartItem.product)).all()

def add_to_cart(db: Session, user_id: int, product_id: int, quantity: int = 1, attributes: str = None):
    try:
        # بررسی موجودی قبل از افزودن
        prod = db.query(models.Product).filter_by(id=product_id).first()
        if not prod or prod.stock < quantity:
            return None # یا raise exception

        item = db.query(models.CartItem).filter_by(
            user_id=user_id, product_id=product_id, selected_attributes=attributes
        ).first()

        if item:
            item.quantity += quantity
        else:
            item = models.CartItem(
                user_id=user_id, product_id=product_id, 
                quantity=quantity, selected_attributes=attributes
            )
            db.add(item)
        
        db.commit()
        db.refresh(item)
        return item
    except SQLAlchemyError:
        db.rollback()
        raise

def remove_from_cart(db: Session, cart_item_id: int) -> bool:
    try:
        count = db.query(models.CartItem).filter_by(id=cart_item_id).delete()
        db.commit()
        return count > 0
    except SQLAlchemyError:
        db.rollback()
        return False

def clear_cart(db: Session, user_id: int):
    try:
        db.query(models.CartItem).filter_by(user_id=user_id).delete(synchronize_session=False)
        db.commit()
    except SQLAlchemyError:
        db.rollback()

# ======================================================================
# 5. سفارشات (Orders)
# ======================================================================

def create_order_from_cart(db: Session, user_id: int, shipping_data: dict) -> models.Order:
    """ساخت سفارش نهایی با کسر موجودی و محاسبه دقیق"""
    try:
        cart_items = get_cart_items(db, user_id)
        if not cart_items:
            raise ValueError("Cart is empty")

        total_amount = 0
        order_items = []

        # بررسی و کسر موجودی + محاسبه قیمت
        for item in cart_items:
            # قیمت: اگر تخفیف دارد، قیمت تخفیفی، وگرنه اصلی
            # (منطق تخفیف را می‌توان اینجا پیچیده‌تر کرد)
            price = item.product.discount_price if (item.product.discount_price and item.product.discount_price > 0) else item.product.price
            
            if item.product.stock < item.quantity:
                raise ValueError(f"Not enough stock for {item.product.name}")
            
            item.product.stock -= item.quantity
            line_total = price * item.quantity
            total_amount += line_total
            
            order_items.append(models.OrderItem(
                product_id=item.product_id,
                quantity=item.quantity,
                price_at_purchase=price,
                selected_attributes=item.selected_attributes
            ))

        # هزینه ارسال
        shipping_cost = int(float(get_setting(db, "shipping_cost", "0")))
        free_limit = int(float(get_setting(db, "free_shipping_limit", "0")))
        
        final_shipping = 0
        if free_limit == 0 or total_amount < free_limit:
            final_shipping = shipping_cost
            total_amount += final_shipping

        order = models.Order(
            user_id=user_id,
            total_amount=total_amount,
            status="pending_payment",
            shipping_address=shipping_data.get("address"),
            phone_number=shipping_data.get("phone"),
            postal_code=shipping_data.get("postal_code"),
            shipping_cost=final_shipping,
            items=order_items
        )
        
        db.add(order)
        # پاکسازی سبد
        db.query(models.CartItem).filter_by(user_id=user_id).delete(synchronize_session=False)
        
        db.commit()
        db.refresh(order)
        
        logger.info(f"Order {order.id} created for user {user_id}")
        return order

    except Exception as e:
        db.rollback()
        logger.error(f"Order creation failed: {e}")
        raise e

def get_filtered_orders(db: Session, status: str = "all") -> List[models.Order]:
    q = db.query(models.Order).options(
        joinedload(models.Order.user),
        selectinload(models.Order.items).joinedload(models.OrderItem.product)
    )
    if status != "all":
        q = q.filter(models.Order.status == status)
    
    return q.order_by(desc(models.Order.created_at)).all()

def update_order_status(db: Session, order_id: int, new_status: str) -> Optional[models.Order]:
    try:
        order = db.query(models.Order).filter_by(id=order_id).first()
        if order:
            order.status = new_status
            db.commit()
            db.refresh(order)
        return order
    except SQLAlchemyError:
        db.rollback()
        return None
        
def get_order_by_id(db: Session, order_id: int) -> Optional[models.Order]:
    return db.query(models.Order).options(
        joinedload(models.Order.items).joinedload(models.OrderItem.product),
        joinedload(models.Order.user)
    ).filter_by(id=order_id).first()

# ======================================================================
# 6. علاقه‌مندی‌ها و آدرس‌ها
# ======================================================================

def toggle_favorite(db: Session, user_id: int, product_id: int) -> bool:
    try:
        fav = db.query(models.Favorite).filter_by(user_id=user_id, product_id=product_id).first()
        if fav:
            db.delete(fav)
            db.commit()
            return False
        else:
            fav = models.Favorite(user_id=user_id, product_id=product_id)
            db.add(fav)
            db.commit()
            return True
    except SQLAlchemyError:
        db.rollback()
        return False

def get_user_favorites(db: Session, user_id: int) -> List[models.Product]:
    return db.query(models.Product).join(models.Favorite).filter(models.Favorite.user_id == user_id).all()

# ======================================================================
# 7. تنظیمات و متفرقه
# ======================================================================

def get_setting(db: Session, key: str, default: str = "") -> str:
    s = db.query(models.Setting).filter_by(key=key).first()
    return s.value if s else default

def set_setting(db: Session, key: str, value: str):
    try:
        s = db.query(models.Setting).filter_by(key=key).first()
        if s: s.value = str(value)
        else: db.add(models.Setting(key=key, value=str(value)))
        db.commit()
    except SQLAlchemyError:
        db.rollback()

def add_product_notification(db: Session, user_id: int, product_id: int):
    try:
        exists = db.query(models.ProductNotification).filter_by(user_id=user_id, product_id=product_id).first()
        if not exists:
            db.add(models.ProductNotification(user_id=user_id, product_id=product_id))
            db.commit()
    except SQLAlchemyError:
        db.rollback()

def process_stock_notifications(db: Session, product_id: int) -> List[int]:
    """یافتن کاربرانی که منتظر موجودی هستند و حذف درخواستشان (برای جلوگیری از نوتیف تکراری)"""
    try:
        notifs = db.query(models.ProductNotification).filter_by(product_id=product_id).all()
        user_ids = [n.user_id for n in notifs]
        if user_ids:
            db.query(models.ProductNotification).filter_by(product_id=product_id).delete(synchronize_session=False)
            db.commit()
        return user_ids
    except SQLAlchemyError:
        db.rollback()
        return []

# ======================================================================
# 8. گزارشات (Analytics)
# ======================================================================

def get_total_revenue(db: Session) -> float:
    return db.query(func.coalesce(func.sum(models.Order.total_amount), 0)).filter(
        models.Order.status.in_(['approved', 'shipped', 'paid'])
    ).scalar()

def get_orders_count_by_status(db: Session, status: str) -> int:
    return db.query(func.count(models.Order.id)).filter_by(status=status).scalar()

def get_sales_stats_by_period(db: Session, days: int = 7) -> Dict[str, List[Any]]:
    """آمار فروش روزانه برای نمودار"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # 1. ساخت اسکلت تاریخ‌ها
    dates_map = { (start_date + timedelta(days=i)).strftime("%Y-%m-%d"): 0 for i in range(days+1) }
    
    # 2. دریافت دیتا از دیتابیس
    # استفاده از func.date (برای SQLite) یا معادل آن برای دیتابیس‌های دیگر
    results = (
        db.query(func.date(models.Order.created_at), func.sum(models.Order.total_amount))
        .filter(
            models.Order.created_at >= start_date,
            models.Order.status.in_(['approved', 'shipped', 'paid'])
        )
        .group_by(func.date(models.Order.created_at))
        .all()
    )
    
    # 3. پر کردن مپ
    for d_str, total in results:
        # در SQLite خروجی func.date استرینگ است
        if d_str in dates_map:
            dates_map[d_str] = total
            
    return {"dates": list(dates_map.keys()), "values": list(dates_map.values())}

def get_category_sales_stats(db: Session) -> Dict[str, Any]:
    res = (
        db.query(models.Category.name, func.count(models.OrderItem.id))
        .join(models.Product, models.Product.category_id == models.Category.id)
        .join(models.OrderItem, models.OrderItem.product_id == models.Product.id)
        .join(models.Order, models.Order.id == models.OrderItem.order_id)
        .filter(models.Order.status.in_(['approved', 'shipped', 'paid']))
        .group_by(models.Category.name)
        .all()
    )
    return {"labels": [r[0] for r in res], "values": [r[1] for r in res]}

def get_db_size_mb() -> float:
    # در محیط واقعی با os.path.getsize فایل دیتابیس محاسبه می‌شود
    # اینجا برای جلوگیری از وابستگی به مسیر فایل، 0 برمی‌گردانیم
    # (در داشبورد ویجت می‌توان با os هندل کرد)
    return 0.0