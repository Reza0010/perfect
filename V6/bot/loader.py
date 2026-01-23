import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from bot.error_handler import global_error_handler
from bot.handlers import (
    start, products_handler, search_handler, cart_handler, main_menu_handler
)

logger = logging.getLogger(__name__)

def setup_application_handlers(app: Application, admin_handler=None):
    """
    ثبت یکجای تمام هندلرهای ربات با اولویت‌بندی صحیح.
    """
    logger.info("Loading bot handlers...")

    # ==================================================================
    # 1. هندلرهای مکالمه (Conversation Handlers) - اولویت بالا
    # ==================================================================
    # این هندلرها باید اول باشند تا وضعیت‌های خاص کاربر را مدیریت کنند
    app.add_handler(search_handler.search_conversation_handler)
    app.add_handler(cart_handler.checkout_conversation_handler)

    # ==================================================================
    # 2. نقطه شروع و منوی اصلی
    # ==================================================================
    # هندلر دستور /start (که در فایل start.py تعریف شده)
    app.add_handler(start.start_handler)
    
    # دکمه بازگشت به منوی اصلی
    app.add_handler(CallbackQueryHandler(start.start, pattern=r"^main_menu$"))

    # ==================================================================
    # 3. مدیریت محصولات و دسته‌بندی‌ها
    # ==================================================================
    # نمایش لیست دسته‌ها (ترکیب پترن‌های مختلف که به یک تابع می‌روند)
    app.add_handler(CallbackQueryHandler(
        products_handler.list_categories, 
        pattern=r"^(products|cat:list:|cat:back:)"
    ))

    # لیست محصولات و صفحه‌بندی
    app.add_handler(CallbackQueryHandler(products_handler.list_products, pattern=r"^(prod:list:|noop$)"))
    
    # نمایش جزئیات محصول
    app.add_handler(CallbackQueryHandler(products_handler.show_product_details, pattern=r"^prod:show:"))

    # ویژگی‌های تعاملی محصول (علاقه‌مندی، اطلاع‌رسانی، انتخاب ویژگی)
    app.add_handler(CallbackQueryHandler(products_handler.toggle_favorite_handler, pattern=r"^fav:toggle:"))
    app.add_handler(CallbackQueryHandler(products_handler.show_favorites, pattern=r"^favorites$"))
    app.add_handler(CallbackQueryHandler(products_handler.notify_me_handler, pattern=r"^notify:"))
    
    # مدیریت متغیرها (Attributes)
    app.add_handler(CallbackQueryHandler(products_handler.start_attribute_selection, pattern=r"^attr:start:"))
    app.add_handler(CallbackQueryHandler(products_handler.confirm_attribute_selection, pattern=r"^attr:sel:"))

    # ==================================================================
    # 4. سبد خرید (Shopping Cart)
    # ==================================================================
    app.add_handler(CallbackQueryHandler(cart_handler.view_cart, pattern=r"^cart:view$"))
    app.add_handler(CallbackQueryHandler(cart_handler.add_to_cart_handler, pattern=r"^cart:add:"))
    app.add_handler(CallbackQueryHandler(cart_handler.update_cart_item_handler, pattern=r"^cart:update:"))
    app.add_handler(CallbackQueryHandler(cart_handler.clear_cart_handler, pattern=r"^cart:clear$"))

    # ==================================================================
    # 5. پروفایل کاربر و صفحات ثابت (User & Static Pages)
    # ==================================================================
    app.add_handler(CallbackQueryHandler(main_menu_handler.handle_user_profile, pattern=r"^user_profile$"))
    app.add_handler(CallbackQueryHandler(main_menu_handler.handle_order_history, pattern=r"^order_history$"))
    
    # مدیریت آدرس‌ها
    app.add_handler(CallbackQueryHandler(main_menu_handler.handle_user_addresses, pattern=r"^user_addresses$"))
    app.add_handler(CallbackQueryHandler(main_menu_handler.handle_delete_address, pattern=r"^addr_del:"))
    
    # صفحات اطلاعاتی
    app.add_handler(CallbackQueryHandler(main_menu_handler.handle_special_offers, pattern=r"^special_offers$"))
    app.add_handler(CallbackQueryHandler(main_menu_handler.handle_track_order, pattern=r"^track_order$"))
    app.add_handler(CallbackQueryHandler(main_menu_handler.handle_support, pattern=r"^support$"))
    app.add_handler(CallbackQueryHandler(main_menu_handler.handle_about_us, pattern=r"^about_us$"))

    # ==================================================================
    # 6. پنل ادمین (تلگرام)
    # ==================================================================
    if admin_handler:
        # هندل کردن دکمه‌های مدیریتی (تایید/رد/ارسال سفارش)
        app.add_handler(CallbackQueryHandler(admin_handler, pattern=r"^adm_(approve|reject|ship):"))

    # ==================================================================
    # 7. مدیریت خطا (Global Error Handler)
    # ==================================================================
    # این باید همیشه آخرین هندلر باشد تا تمام خطاهای قبلی را بگیرد
    app.add_error_handler(global_error_handler)
    
    logger.info("✅ All handlers registered successfully.")