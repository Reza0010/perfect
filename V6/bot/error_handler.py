import logging
import html
import json
import traceback
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from config import ADMIN_USER_IDS

logger = logging.getLogger(__name__)

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    هندلر سراسری خطاها.
    این تابع هر خطایی (Exception) که در حین اجرای ربات رخ دهد را دریافت کرده،
    لاگ می‌کند، به ادمین‌ها گزارش می‌دهد و به کاربر پیام مناسب نمایش می‌دهد.
    """
    # 1. ثبت خطا در فایل لاگ سرور
    logger.error("Exception while handling an update:", exc_info=context.error)

    # 2. آماده‌سازی متن خطا (Traceback)
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    # 3. فرمت‌دهی داده‌های آپدیت (اطلاعات پیامی که باعث خطا شده)
    update_str = str(update)
    if isinstance(update, Update):
        try:
            # استفاده از default=str برای جلوگیری از خطا در سریالایز کردن آبجکت‌های خاص مثل datetime
            update_dict = update.to_dict()
            update_str = json.dumps(update_dict, indent=2, ensure_ascii=False, default=str)
        except Exception:
            # اگر تبدیل به جیسون شکست خورد، همان رشته ساده را نگه می‌داریم
            pass

    # 4. ساخت پیام گزارش برای ادمین
    # محدودیت تلگرام ۴۰۹۶ کاراکتر است. ما بخش‌های مختلف را برش می‌زنیم.
    header = (
        f"🔴 <b>گزارش خطای بحرانی ربات</b>\n"
        f"⚠️ <b>نوع خطا:</b> <code>{html.escape(str(context.error))}</code>\n\n"
    )
    
    # اختصاص حدود 1000 کاراکتر به متن آپدیت و باقی‌مانده به تریس‌بک
    update_section = f"<b>Update Data:</b>\n<pre>{html.escape(update_str[:1000])}</pre>\n\n"
    traceback_section = f"<b>Traceback:</b>\n<pre>{html.escape(tb_string[-2500:])}</pre>"

    full_admin_message = header + update_section + traceback_section

    # 5. ارسال گزارش به ادمین‌ها
    for admin_id in ADMIN_USER_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id, 
                text=full_admin_message, 
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Failed to send error report to admin {admin_id}: {e}")

    # 6. اطلاع‌رسانی به کاربر (Graceful Failure)
    if isinstance(update, Update):
        # الف) اگر خطا روی دکمه شیشه‌ای رخ داده، لودینگ را متوقف کن
        if update.callback_query:
            try:
                await update.callback_query.answer("⚠️ خطای سیستمی رخ داد.", show_alert=True)
            except Exception:
                pass # ممکن است کوئری قدیمی باشد

        # ب) ارسال پیام متنی به کاربر
        if update.effective_message:
            user_text = (
                "⚠️ <b>متاسفانه مشکلی در پردازش درخواست شما پیش آمد.</b>\n\n"
                "گزارش این خطا برای تیم فنی ارسال شد و به زودی برطرف خواهد شد.\n"
                "لطفاً چند لحظه دیگر تلاش کنید یا با دستور /start به منوی اصلی برگردید."
            )
            try:
                await update.effective_message.reply_text(user_text, parse_mode=ParseMode.HTML)
            except Exception:
                pass # اگر نتوانیم به کاربر پیام دهیم (مثلاً بلاک کرده باشد)، نادیده می‌گیریم