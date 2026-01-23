import logging
import html
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.error import BadRequest

from bot import keyboards, responses
from bot.utils import run_db
from db import crud

logger = logging.getLogger(__name__)

# ==============================================================================
# تابع کمکی (Helper Function) برای مدیریت ارسال/ویرایش پیام
# ==============================================================================
async def _safe_edit(update: Update, text: str, reply_markup: InlineKeyboardMarkup):
    """
    سعی می‌کند پیام فعلی را ویرایش کند. 
    اگر پیام قبلی عکس باشد (که متن آن قابل ویرایش به این شکل نیست)، 
    آن را حذف و پیام متنی جدید ارسال می‌کند.
    """
    query = update.callback_query
    try:
        await query.edit_message_text(
            text=text, 
            reply_markup=reply_markup, 
            parse_mode='HTML'
        )
    except BadRequest:
        # معمولاً خطای "Message is not modified" یا تلاش برای تبدیل عکس به متن
        try:
            await query.message.delete()
            await query.message.reply_text(
                text=text, 
                reply_markup=reply_markup, 
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error in _safe_edit: {e}")

# ==============================================================================
# هندلرها (Handlers)
# ==============================================================================

async def handle_special_offers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش پیشنهادات ویژه"""
    query = update.callback_query
    await query.answer()
    
    # فعلاً متن ثابت است، می‌توان بعداً از دیتابیس خواند
    text = f"🔥 <b>پیشنهادهای ویژه</b>\n{responses.get_divider()}\nدر حال حاضر پیشنهاد فعالی وجود ندارد."
    
    await _safe_edit(update, text, keyboards.get_main_menu_keyboard())

async def handle_track_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پیگیری آخرین سفارش کاربر"""
    query = update.callback_query
    await query.answer()
    
    # دریافت آخرین سفارش (لیست سفارشات با محدودیت ۱)
    orders = await run_db(crud.get_user_orders, update.effective_user.id)
    last_order = orders[0] if orders else None
    
    if last_order:
        timeline = responses.get_tracking_timeline(last_order.status)
        trk = f"\n📦 <b>کد رهگیری:</b> <code>{last_order.tracking_code}</code>" if last_order.tracking_code else ""
        
        text = (
            f"📋 <b>پیگیری آخرین سفارش:</b>\n"
            f"🆔 شناسه: <code>{last_order.id}</code>\n"
            f"💰 مبلغ: {responses.format_price(last_order.total_amount)}\n"
            f"📅 تاریخ: {last_order.created_at.strftime('%Y-%m-%d')}\n\n"
            f"{timeline}{trk}"
        )
    else:
        text = "❌ شما هنوز سفارشی ثبت نکرده‌اید."
    
    await _safe_edit(update, text, keyboards.get_main_menu_keyboard())

async def handle_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش اطلاعات پشتیبانی"""
    query = update.callback_query
    await query.answer()
    
    supp_id = await run_db(crud.get_setting, "support_id", "@Admin")
    text = responses.SUPPORT_TEXT.format(support_id=supp_id, divider=responses.get_divider())
    
    back_btn = InlineKeyboardMarkup([[InlineKeyboardButton(responses.BACK_BUTTON, callback_data="main_menu")]])
    await _safe_edit(update, text, back_btn)

async def handle_about_us(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش درباره ما"""
    query = update.callback_query
    await query.answer()
    
    name = await run_db(crud.get_setting, "shop_name", "فروشگاه ما")
    phone = await run_db(crud.get_setting, "contact_phone", "تعریف نشده")
    addr = await run_db(crud.get_setting, "shop_address", "تعریف نشده")
    
    text = responses.ABOUT_US_TEXT.format(
        shop_name=name, 
        phone=phone, 
        address=addr, 
        divider=responses.get_divider()
    )
    
    back_btn = InlineKeyboardMarkup([[InlineKeyboardButton(responses.BACK_BUTTON, callback_data="main_menu")]])
    await _safe_edit(update, text, back_btn)

async def handle_user_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش پروفایل کاربری"""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    
    # اطمینان از وجود کاربر در دیتابیس
    db_user = await run_db(crud.get_or_create_user, user.id, user.full_name)
    stats = await run_db(crud.get_user_stats, user.id) # استفاده از تابع جدید stats در crud
    
    # ایمن‌سازی نام کاربر برای HTML
    safe_name = html.escape(user.full_name or "کاربر")
    join_date = stats.get("join_date").strftime("%Y/%m/%d") if stats.get("join_date") else "-"
    
    text = responses.USER_PROFILE_DASHBOARD.format(
        divider=responses.get_divider(),
        user_id=user.id,
        full_name=safe_name,
        phone=db_user.phone_number or "ثبت نشده", # اصلاح نام فیلد (phone_number صحیح است)
        join_date=join_date,
        order_count=stats.get("total_orders", 0),
        total_spent=responses.format_price(stats.get("total_spent", 0))
    )
    
    await _safe_edit(update, text, keyboards.get_user_profile_keyboard())

async def handle_order_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش تاریخچه سفارشات"""
    query = update.callback_query
    await query.answer()
    
    orders = await run_db(crud.get_user_orders, update.effective_user.id) # استفاده از تابع صحیح
    
    if not orders:
        history_text = "❌ شما هنوز هیچ سفارشی ثبت نکرده‌اید."
    else:
        lines = []
        for o in orders[:10]: # نمایش ۱۰ سفارش آخر
            icon = "✅" if o.status in ["shipped", "approved", "paid"] else "⏳"
            # تبدیل وضعیت به متن فارسی
            status_map = {
                "pending_payment": "در انتظار پرداخت",
                "approved": "تایید شده",
                "shipped": "ارسال شده",
                "rejected": "رد شده"
            }
            st_text = status_map.get(o.status, o.status)
            lines.append(f"{icon} <b>#{o.id}</b> | {responses.format_price(o.total_amount)} | {st_text}")
        
        history_text = "\n".join(lines)
            
    text = responses.ORDER_HISTORY_LIST.format(
        divider=responses.get_divider(), 
        orders_text=history_text
    )
    
    await _safe_edit(update, text, keyboards.get_order_history_keyboard())

async def handle_user_addresses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت آدرس‌ها"""
    query = update.callback_query
    await query.answer()
    
    addrs = await run_db(crud.get_user_addresses, update.effective_user.id)
    kbd = keyboards.get_address_book_keyboard(addrs, is_checkout=False)
    
    await _safe_edit(update, responses.ADDRESS_MANAGEMENT_TITLE, kbd)

async def handle_delete_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف آدرس"""
    query = update.callback_query
    try:
        addr_id = int(query.data.split(':')[1])
        
        # استفاده از run_db برای عملیات دیتابیس
        deleted = await run_db(crud.delete_user_address, addr_id, update.effective_user.id)
        
        if deleted:
            await query.answer("✅ آدرس با موفقیت حذف شد.")
        else:
            await query.answer("❌ خطا در حذف آدرس.", show_alert=True)
            
        # رفرش لیست آدرس‌ها
        await handle_user_addresses(update, context)
        
    except (IndexError, ValueError) as e:
        logger.error(f"Address delete error: {e}")
        await query.answer("خطا در پردازش درخواست.")