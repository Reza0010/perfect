import math
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, 
    ConversationHandler, 
    MessageHandler, 
    filters, 
    CallbackQueryHandler, 
    CommandHandler
)
from telegram.error import BadRequest

from bot.utils import run_db
from db import crud
from bot import keyboards, responses

logger = logging.getLogger(__name__)

# وضعیت‌های گفتگو
SEARCH_QUERY_STATE, APPLY_FILTER_STATE = range(2)

# تنظیمات
PRODUCTS_PER_PAGE = 6

async def _safe_reply(update: Update, text: str, reply_markup: InlineKeyboardMarkup = None):
    """تابع کمکی برای ارسال یا ویرایش پیام بدون خطا"""
    try:
        if update.callback_query:
            # اگر کال‌بک باشد، سعی می‌کنیم ویرایش کنیم
            try:
                await update.callback_query.edit_message_text(
                    text=text, 
                    reply_markup=reply_markup, 
                    parse_mode='HTML'
                )
            except BadRequest:
                # اگر پیام قابل ویرایش نبود (مثلاً عکس‌دار بود یا خیلی قدیمی)، حذف و ارسال جدید
                await update.callback_query.message.delete()
                await update.callback_query.message.reply_text(
                    text=text, 
                    reply_markup=reply_markup, 
                    parse_mode='HTML'
                )
        else:
            # اگر پیام معمولی باشد
            await update.message.reply_text(
                text=text, 
                reply_markup=reply_markup, 
                parse_mode='HTML'
            )
    except Exception as e:
        logger.error(f"Error in safe_reply: {e}")

async def start_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """شروع پروسه جستجو"""
    user = update.effective_user
    logger.info(f"User {user.id} started search.")
    
    if update.callback_query:
        await update.callback_query.answer()

    kbd = InlineKeyboardMarkup([
        [InlineKeyboardButton(responses.BACK_BUTTON, callback_data="main_menu")]
    ])
    
    await _safe_reply(update, responses.SEARCH_PROMPT, kbd)
    return SEARCH_QUERY_STATE

async def handle_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """دریافت متن جستجو از کاربر و نمایش فیلترها"""
    query_text = update.message.text.strip()
    
    if len(query_text) < 2:
        await update.message.reply_text("⚠️ لطفاً حداقل ۲ حرف وارد کنید:")
        return SEARCH_QUERY_STATE
    
    # ذخیره کوئری در حافظه موقت کاربر
    context.user_data['search_query'] = query_text
    
    # نمایش کیبورد فیلترها (ارزان‌ترین، گران‌ترین و...)
    kbd = keyboards.get_search_filter_keyboard(query_text)
    
    msg_text = f"{responses.SEARCH_RESULT_TITLE.format(query=query_text)}\n\n🔻 لطفاً نوع مرتب‌سازی را انتخاب کنید:"
    await update.message.reply_text(msg_text, reply_markup=kbd, parse_mode='HTML')
    
    return APPLY_FILTER_STATE

async def show_search_results(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """نمایش نتایج جستجو با قابلیت صفحه‌بندی و فیلتر"""
    query = update.callback_query
    await query.answer()
    
    try:
        # فرمت دیتا: search:filter_type:query:sort_key:page_num
        # مثال: search:page:گوشی:price_asc:2
        parts = query.data.split(':')
        
        action_type = parts[1] # 'filter' or 'page'
        search_query = parts[2]
        sort_by = parts[3]
        
        # تعیین شماره صفحه
        page = 1
        if action_type == "page" and len(parts) > 4:
            page = int(parts[4])
        
        # فراخوانی دیتابیس (فرض بر این است که crud.advanced_search_products وجود دارد)
        # اگر crud شما صفحه‌بندی داخلی ندارد، ما کل نتایج را می‌گیریم و اینجا اسلایس می‌کنیم
        all_products = await run_db(
            crud.advanced_search_products, 
            query=search_query, 
            # نگاشت sort_by به پارامترهای crud در صورت نیاز
        )
        
        # اعمال مرتب‌سازی دستی اگر دیتابیس انجام نداده باشد
        if sort_by == "price_asc":
            all_products.sort(key=lambda p: p.price)
        elif sort_by == "price_desc":
            all_products.sort(key=lambda p: p.price, reverse=True)
        elif sort_by == "newest":
            all_products.sort(key=lambda p: p.created_at, reverse=True)
            
        # منطق صفحه‌بندی پایتونی
        total_items = len(all_products)
        total_pages = max(1, math.ceil(total_items / PRODUCTS_PER_PAGE))
        
        # اعتبارسنجی صفحه
        if page > total_pages: page = total_pages
        if page < 1: page = 1
        
        start_idx = (page - 1) * PRODUCTS_PER_PAGE
        end_idx = start_idx + PRODUCTS_PER_PAGE
        current_page_products = all_products[start_idx:end_idx]
        
        # ساخت کیبورد نتایج
        kbd = keyboards.build_search_results_keyboard(
            products=current_page_products,
            query=search_query,
            sort_by=sort_by,
            current_page=page,
            total_pages=total_pages
        )
        
        if current_page_products:
            msg_text = f"🔎 نتایج جستجو برای: <b>{search_query}</b>\n📄 صفحه {page} از {total_pages}\n\nتعداد کل نتایج: {total_items} عدد"
        else:
            msg_text = responses.SEARCH_NO_RESULT
            
        await _safe_reply(update, msg_text, kbd)
        
    except Exception as e:
        logger.error(f"Search Error: {e}")
        await query.message.reply_text("⚠️ خطایی در جستجو رخ داد. لطفاً دوباره تلاش کنید.")
        return ConversationHandler.END

    return APPLY_FILTER_STATE

async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """لغو عملیات جستجو و بازگشت به منوی اصلی"""
    kbd = keyboards.get_main_menu_keyboard()
    msg = "جستجو لغو شد. به منوی اصلی بازگشتید."
    
    await _safe_reply(update, msg, kbd)
    return ConversationHandler.END

# تعریف هندلر مکالمه (ConversationHandler)
search_conversation_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(start_search, pattern=r'^search:start$'),
        CommandHandler("search", start_search)
    ],
    states={
        SEARCH_QUERY_STATE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_query)
        ],
        APPLY_FILTER_STATE: [
            # هندل کردن تغییر فیلتر یا صفحه
            CallbackQueryHandler(show_search_results, pattern=r'^search:(filter|page):'),
            # دکمه شروع مجدد جستجو
            CallbackQueryHandler(start_search, pattern=r'^search:start$')
        ],
    },
    fallbacks=[
        CallbackQueryHandler(cancel_search, pattern=r'^main_menu$'),
        CommandHandler("cancel", cancel_search),
        CommandHandler("start", cancel_search) # اگر وسط جستجو استارت زد
    ],
    allow_reentry=True,
    per_chat=True,
    per_user=True,
)