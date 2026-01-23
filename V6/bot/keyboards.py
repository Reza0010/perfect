from typing import List, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from db import models
from . import responses

# ==============================================================================
# تابع کمکی (Helper Function) برای چیدمان گرید
# ==============================================================================
def _build_grid(buttons: List[InlineKeyboardButton], n_cols: int) -> List[List[InlineKeyboardButton]]:
    """تبدیل یک لیست تخت از دکمه‌ها به یک ساختار چند ستونه (Grid)."""
    return [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]

# ==============================================================================
# بخش ۱: منوی اصلی (Main Menu)
# ==============================================================================
def get_main_menu_keyboard(channel_url: Optional[str] = None) -> InlineKeyboardMarkup:
    """
    منوی شبکه‌ای و مدرن
    ردیف ۱: محصولات (بزرگ)
    ردیف ۲: جستجو | پیشنهادات (متوسط)
    ردیف ۳: سبد | پیگیری | پروفایل (کوچک)
    ردیف ۴: پشتیبانی | درباره ما
    """
    keyboard = [
        # ردیف اول: دکمه اصلی و بزرگ
        [InlineKeyboardButton(f"🛍 {responses.PRODUCTS_BUTTON.replace('🛍 ', '')}", callback_data="products")],
        
        # ردیف دوم: دو ستونه
        [
            InlineKeyboardButton(responses.SEARCH_BUTTON, callback_data="search:start"),
            InlineKeyboardButton(responses.SPECIAL_OFFERS_BUTTON, callback_data="special_offers")
        ],
        
        # ردیف سوم: سه ستونه (دسترسی سریع)
        [
            InlineKeyboardButton("🛒 سبد", callback_data="cart:view"),
            InlineKeyboardButton("📦 پیگیری", callback_data="track_order"),
            InlineKeyboardButton("👤 من", callback_data="user_profile")
        ],
        
        # ردیف چهارم: اطلاعات
        [
            InlineKeyboardButton(responses.SUPPORT_BUTTON, callback_data="support"),
            InlineKeyboardButton(responses.ABOUT_US_BUTTON, callback_data="about_us")
        ]
    ]
    
    if channel_url and channel_url.startswith("http"):
        keyboard.append([InlineKeyboardButton("📢 عضویت در کانال تخفیف‌ها", url=channel_url)])
        
    return InlineKeyboardMarkup(keyboard)

# ==============================================================================
# بخش ۲: محصولات و دسته‌بندی‌ها (Products & Categories)
# ==============================================================================
def build_category_keyboard(categories: List[models.Category], parent_id: Optional[int] = None) -> InlineKeyboardMarkup:
    """کیبورد انتخاب دسته‌بندی (پشتیبانی از زیرمجموعه)"""
    if not categories:
        # اگر دسته‌ای نبود، دکمه بازگشت ساده
        back_cb = f"cat:list:{parent_id}" if parent_id else "main_menu"
        return InlineKeyboardMarkup([[InlineKeyboardButton(responses.BACK_BUTTON, callback_data=back_cb)]])

    buttons = [InlineKeyboardButton(cat.name, callback_data=f"cat:list:{cat.id}") for cat in categories]
    keyboard = _build_grid(buttons, 2) # دو ستونه
    
    # دکمه بازگشت هوشمند
    if parent_id:
        # اگر زیرمجموعه هستیم، بازگشت به والد (یا ریشه)
        # نکته: برای سادگی اینجا به ریشه برمی‌گردیم، اگر ساختار عمیق‌تر دارید باید آی‌دی والدِ والد را پاس دهید
        back_cb = "cat:back:root" # یا products
    else:
        back_cb = "main_menu"
        
    keyboard.append([InlineKeyboardButton(responses.BACK_BUTTON, callback_data=back_cb)])
    return InlineKeyboardMarkup(keyboard)

def build_product_keyboard(products: List[models.Product], cat_id: int, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """لیست محصولات با صفحه‌بندی"""
    keyboard = []
    
    for product in products:
        price_str = f"{int(product.price):,}"
        keyboard.append([InlineKeyboardButton(f"{product.name} | {price_str} ت", callback_data=f"prod:show:{product.id}")])

    # کنترلر صفحه‌بندی
    if total_pages > 1:
        nav_row = []
        if page > 1:
            nav_row.append(InlineKeyboardButton("◀️ قبلی", callback_data=f"prod:list:{cat_id}:{page-1}"))
        
        nav_row.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="noop"))
        
        if page < total_pages:
            nav_row.append(InlineKeyboardButton("بعدی ▶️", callback_data=f"prod:list:{cat_id}:{page+1}"))
        
        keyboard.append(nav_row)

    # بازگشت به لیست دسته‌ها
    keyboard.append([InlineKeyboardButton(responses.BACK_BUTTON, callback_data=f"cat:list:{cat_id}")])
    return InlineKeyboardMarkup(keyboard)

def get_product_detail_keyboard(product: models.Product, is_favorite: bool, cart_qty: int, bot_username: str) -> InlineKeyboardMarkup:
    """کیبورد صفحه جزئیات محصول"""
    keyboard = []
    
    # دکمه خرید / انتخاب ویژگی / خبرم کن
    if product.stock > 0:
        label = f"🛒 افزودن به سبد ({cart_qty})" if cart_qty > 0 else "🛒 افزودن به سبد خرید"
        
        # اگر محصول متغیر یا ویژگی دارد، باید اول انتخاب کند
        if product.variants or product.attributes:
            cb_data = f"attr:start:{product.id}" # هدایت به منوی انتخاب ویژگی
        else:
            cb_data = f"cart:add:{product.id}" # افزودن مستقیم
            
        keyboard.append([InlineKeyboardButton(label, callback_data=cb_data)])
    else:
        keyboard.append([InlineKeyboardButton("🔔 موجود شد خبرم کن", callback_data=f"notify:{product.id}")])

    # دکمه‌های تعاملی
    fav_text = "❤️ حذف از علاقه‌مندی" if is_favorite else "🤍 افزودن به علاقه‌مندی"
    share_url = f"https://t.me/share/url?url=https://t.me/{bot_username}?start=p_{product.id}"
    
    keyboard.append([
        InlineKeyboardButton(fav_text, callback_data=f"fav:toggle:{product.id}"),
        InlineKeyboardButton("🔗 اشتراک‌گذاری", url=share_url)
    ])
    
    # بازگشت
    back_cb = f"prod:list:{product.category_id}:1" if product.category_id else "products"
    keyboard.append([InlineKeyboardButton(responses.BACK_BUTTON, callback_data=back_cb)])
    
    return InlineKeyboardMarkup(keyboard)

# ==============================================================================
# بخش ۳: سبد خرید (Shopping Cart)
# ==============================================================================
def view_cart_keyboard(items: List[models.CartItem]) -> InlineKeyboardMarkup:
    """کیبورد مدیریت سبد خرید"""
    keyboard = []
    
    for item in items:
        # نام محصول (برای اطلاع)
        keyboard.append([InlineKeyboardButton(f"🔸 {item.product.name}", callback_data=f"prod:show:{item.product_id}")])
        
        # کنترلر تعداد (- 1 +)
        keyboard.append([
            InlineKeyboardButton("➖", callback_data=f"cart:update:{item.product_id}:-1"),
            InlineKeyboardButton(f"{item.quantity} عدد", callback_data="noop"),
            InlineKeyboardButton("➕", callback_data=f"cart:update:{item.product_id}:1"),
        ])

    if items:
        keyboard.append([
            InlineKeyboardButton("🗑 خالی کردن سبد", callback_data="cart:clear"),
            InlineKeyboardButton("✅ نهایی‌سازی خرید", callback_data="cart:checkout")
        ])

    keyboard.append([InlineKeyboardButton(responses.MAIN_MENU_BUTTON, callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_address_book_keyboard(addresses: List[models.UserAddress], is_checkout: bool = True) -> InlineKeyboardMarkup:
    """لیست آدرس‌ها (برای پروفایل یا هنگام خرید)"""
    keyboard = []
    
    for addr in addresses:
        # در حالت خرید، کلیک روی آدرس آن را انتخاب می‌کند
        # در پروفایل، دکمه‌ای کاری نمی‌کند (فقط نمایش) و دکمه حذف جداست
        cb_action = f"use_addr:{addr.id}" if is_checkout else "noop"
        row = [InlineKeyboardButton(f"📍 {addr.title}: {addr.address_text[:20]}...", callback_data=cb_action)]
        
        if not is_checkout:
            row.append(InlineKeyboardButton("❌ حذف", callback_data=f"addr_del:{addr.id}"))
            
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("➕ ثبت آدرس جدید", callback_data="new_address")])
    
    back_to = "cart:view" if is_checkout else "user_profile"
    keyboard.append([InlineKeyboardButton(responses.BACK_BUTTON, callback_data=back_to)])
    
    return InlineKeyboardMarkup(keyboard)

# ==============================================================================
# بخش ۴: پروفایل و تاریخچه (User Profile)
# ==============================================================================
def get_user_profile_keyboard() -> InlineKeyboardMarkup:
    """منوی پروفایل کاربری"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 تاریخچه سفارشات", callback_data="order_history")],
        [InlineKeyboardButton("📍 مدیریت آدرس‌ها", callback_data="user_addresses")],
        [InlineKeyboardButton(responses.MAIN_MENU_BUTTON, callback_data="main_menu")]
    ])

def get_order_history_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت به پروفایل", callback_data="user_profile")]
    ])

# ==============================================================================
# بخش ۵: جستجو و فیلتر (Search & Filter)
# ==============================================================================
def get_search_filter_keyboard(query: str) -> InlineKeyboardMarkup:
    """فیلترهای مرتب‌سازی جستجو"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💰 ارزان‌ترین", callback_data=f"search:filter:{query}:price_asc"),
            InlineKeyboardButton("💎 گران‌ترین", callback_data=f"search:filter:{query}:price_desc")
        ],
        [
            InlineKeyboardButton("🆕 جدیدترین", callback_data=f"search:filter:{query}:newest"),
            InlineKeyboardButton("🔥 پرفروش‌ترین", callback_data=f"search:filter:{query}:top_seller")
        ],
        [InlineKeyboardButton(responses.MAIN_MENU_BUTTON, callback_data="main_menu")]
    ])

def build_search_results_keyboard(products: List[models.Product], query: str, sort_by: str, current_page: int, total_pages: int) -> InlineKeyboardMarkup:
    """نمایش نتایج جستجو با صفحه‌بندی"""
    keyboard = []
    
    for p in products:
        keyboard.append([InlineKeyboardButton(f"{p.name} | {int(p.price):,} ت", callback_data=f"prod:show:{p.id}")])
        
    if total_pages > 1:
        nav = []
        if current_page > 1:
            nav.append(InlineKeyboardButton("◀️", callback_data=f"search:page:{query}:{sort_by}:{current_page-1}"))
        
        nav.append(InlineKeyboardButton(f"{current_page}/{total_pages}", callback_data="noop"))
        
        if current_page < total_pages:
            nav.append(InlineKeyboardButton("▶️", callback_data=f"search:page:{query}:{sort_by}:{current_page+1}"))
        
        keyboard.append(nav)
        
    keyboard.append([InlineKeyboardButton("🔍 جستجوی مجدد", callback_data="search:start")])
    keyboard.append([InlineKeyboardButton(responses.MAIN_MENU_BUTTON, callback_data="main_menu")])
    
    return InlineKeyboardMarkup(keyboard)

# ==============================================================================
# بخش ۶: ادمین و سایر (Admin & Misc)
# ==============================================================================
def get_contact_keyboard() -> ReplyKeyboardMarkup:
    """دکمه ارسال شماره موبایل"""
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📱 ارسال شماره موبایل من", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_admin_order_keyboard(order_id: int, user_id: int) -> InlineKeyboardMarkup:
    """پنل مدیریت سفارش برای ادمین در تلگرام"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تایید سفارش", callback_data=f"adm_approve:{order_id}"),
            InlineKeyboardButton("❌ رد سفارش", callback_data=f"adm_reject:{order_id}")
        ],
        [InlineKeyboardButton("🚚 ثبت کد رهگیری / ارسال", callback_data=f"adm_ship:{order_id}")],
        [InlineKeyboardButton("👤 پیام به مشتری", url=f"tg://user?id={user_id}")]
    ])