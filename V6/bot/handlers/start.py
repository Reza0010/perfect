import logging
import asyncio
from pathlib import Path
from typing import Optional

from telegram import Update, InlineKeyboardMarkup, InputMediaPhoto, constants
from telegram.ext import ContextTypes, CommandHandler
from telegram.error import BadRequest

from bot import responses, keyboards
from bot.utils import run_db
from db import crud
from config import BASE_DIR

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    هندلر دستور /start و دکمه بازگشت به منوی اصلی.
    از Deep Linking برای نمایش مستقیم محصول پشتیبانی می‌کند.
    """
    user = update.effective_user
    chat_id = update.effective_chat.id
    if not user:
        return

    # 1. دریافت اطلاعات از دیتابیس به صورت همزمان (Parallel Fetching)
    # این کار سرعت لود شدن منو را چند برابر می‌کند
    try:
        results = await asyncio.gather(
            run_db(crud.get_or_create_user, telegram_id=user.id, full_name=user.full_name or "کاربر", username=user.username),
            run_db(crud.get_setting, "shop_name", "فروشگاه ما"),
            run_db(crud.get_setting, "shop_is_open", "true"),
            run_db(crud.get_setting, "welcome_message", ""),
            run_db(crud.get_setting, "welcome_image", ""),
            run_db(crud.get_setting, "channel_link", "")
        )
        
        # باز کردن نتایج (Unpacking)
        _, shop_name, shop_is_open, db_welcome, banner_rel_path, channel_url = results

    except Exception as e:
        logger.error(f"Start Handler DB Error: {e}")
        await context.bot.send_message(chat_id=chat_id, text="⚠️ خطای موقت در ارتباط با سرور. لطفاً مجدداً تلاش کنید.")
        return

    # 2. بررسی Deep Linking (لینک مستقیم به محصول)
    # مثال: t.me/bot?start=p_123
    if context.args and context.args[0].startswith('p_'):
        try:
            prod_id = int(context.args[0].replace('p_', ''))
            
            # شبیه‌سازی آبجکت برای هندلر محصول (بدون تغییر ساختار فعلی شما)
            # نکته: روش استانداردتر فراخوانی مستقیم تابع است، اما برای حفظ سازگاری کد شما این روش را بهینه کردم
            update.callback_query = type('FakeQuery', (object,), {
                'data': f"prod:show:{prod_id}",
                'answer': lambda *a, **k: None, # تابع خالی برای جلوگیری از خطا
                'message': update.message,
                'from_user': user,
                'id': 'fake_id'
            })
            
            # ایمپورت داخلی برای جلوگیری از چرخه وابستگی (Circular Import)
            from bot.handlers.products_handler import show_product_details
            await show_product_details(update, context)
            return
        except ValueError:
            pass # اگر آیدی محصول معتبر نبود، منوی اصلی را نشان بده
        except Exception as e:
            logger.error(f"Deep Link Error: {e}")

    # 3. آماده‌سازی متن خوش‌آمدگویی
    welcome_text = db_welcome if db_welcome else responses.WELCOME_MESSAGE
    welcome_text = welcome_text.replace("{user_name}", user.first_name or "کاربر").replace("{shop_name}", shop_name)
    
    # هشدار بسته بودن فروشگاه
    if shop_is_open.lower() == "false":
        welcome_text += f"\n\n{responses.get_divider()}\n⛔ <b>فروشگاه در حال حاضر بسته است و سفارش‌گیری انجام نمی‌شود.</b>"

    # کیبورد منوی اصلی
    kbd = keyboards.get_main_menu_keyboard(channel_url=channel_url)
    
    # بررسی وجود بنر
    full_photo_path = (Path(BASE_DIR) / banner_rel_path) if banner_rel_path else None
    has_banner = full_photo_path and full_photo_path.exists()

    # مدیریت Callback Query (اگر کاربر روی دکمه "خانه" کلیک کرده باشد)
    query = update.callback_query
    if query:
        await query.answer()

    # 4. ارسال یا ویرایش پیام (Smart Sending Logic)
    try:
        # حالت اول: ارسال عکس (بنر دارد)
        if has_banner:
            # اگر پیام قبلی وجود دارد، آن را حذف کن تا عکس جدید پایین بیاید (تمیزتر است)
            # تلگرام اجازه تبدیل متن به عکس در ادیت را نمی‌دهد، پس حذف و ارسال بهتر است
            if query and query.message:
                await query.message.delete()
            
            with open(full_photo_path, 'rb') as photo:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=welcome_text,
                    reply_markup=kbd,
                    parse_mode=constants.ParseMode.HTML
                )
        
        # حالت دوم: بدون عکس (فقط متن)
        else:
            if query and query.message:
                # اگر پیام قبلی عکس داشت، باید حذف شود چون می‌خواهیم متن بفرستیم
                if query.message.photo:
                    await query.message.delete()
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=welcome_text,
                        reply_markup=kbd,
                        parse_mode=constants.ParseMode.HTML
                    )
                else:
                    # اگر پیام قبلی متن بود، فقط ویرایشش می‌کنیم (بدون پرش صفحه)
                    await query.edit_message_text(
                        text=welcome_text,
                        reply_markup=kbd,
                        parse_mode=constants.ParseMode.HTML
                    )
            else:
                # دستور /start معمولی
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=welcome_text,
                    reply_markup=kbd,
                    parse_mode=constants.ParseMode.HTML
                )

    except BadRequest as e:
        # نادیده گرفتن خطای "Message is not modified"
        if "Message is not modified" in str(e):
            pass
        else:
            logger.error(f"Error sending start message: {e}")

# تعریف هندلر
start_handler = CommandHandler("start", start)