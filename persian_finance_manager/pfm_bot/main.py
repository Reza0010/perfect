import logging
import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, ConversationHandler, CallbackQueryHandler
from sqlalchemy.orm import Session
from sqlalchemy import func

# افزودن مسیر ریشه پروژه به sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pfm_core import parser, models

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
try:
    raw_ids = os.getenv("ALLOWED_USER_IDS", "")
    ALLOWED_USER_IDS = [int(user_id) for user_id in raw_ids.split(',') if user_id.strip()]
except (ValueError, AttributeError):
    ALLOWED_USER_IDS = []

CONFIRMATION = range(1)


def get_db():
    """یک نشست پایگاه داده ایجاد می‌کند."""
    db = models.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- توابع منو و گزارش‌دهی (بدون تغییر) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [[InlineKeyboardButton("📊 گزارش‌گیری", callback_data='report_menu')], [InlineKeyboardButton(" راهنما ℹ️", callback_data='help')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text("سلام! به ربات مدیریت مالی خوش آمدید. لطفاً یک گزینه را انتخاب کنید:", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(text="منوی اصلی:", reply_markup=reply_markup)

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if query.data == 'main_menu': await start(update, context)
    elif query.data == 'report_menu':
        keyboard = [[InlineKeyboardButton("روزانه", callback_data='report_daily'), InlineKeyboardButton("هفتگی", callback_data='report_weekly')], [InlineKeyboardButton("ماهانه", callback_data='report_monthly')], [InlineKeyboardButton(" بازگشت ⬅️", callback_data='main_menu')]]
        await query.edit_message_text(text="لطفاً دوره گزارش را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data.startswith('report_'): await generate_report(query, query.data.split('_')[1])
    elif query.data == 'help':
        help_text = "**راهنمای ربات**\n\n**ثبت تراکنش:**\nتراکنش خود را به فارسی تایپ کنید. مثال:\n<i>خرید قهوه ۵۰ هزار تومان از حساب ملت</i>\n\n**گزارش‌گیری:**\nاز دستور /start برای دسترسی به منو استفاده کنید."
        keyboard = [[InlineKeyboardButton(" بازگشت ⬅️", callback_data='main_menu')]]
        await query.edit_message_text(text=help_text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))

async def generate_report(query, period: str):
    db = next(get_db())
    end_date = datetime.now()
    if period == 'daily': start_date, period_farsi = end_date - timedelta(days=1), "۲۴ ساعت گذشته"
    elif period == 'weekly': start_date, period_farsi = end_date - timedelta(days=7), "۷ روز گذشته"
    elif period == 'monthly': start_date, period_farsi = end_date - timedelta(days=30), "۳۰ روز گذشته"
    else: return
    try:
        start_date_str = start_date.strftime('%Y-%m-%d %H:%M:%S')
        income = db.query(func.sum(models.Transaction.amount)).filter(models.Transaction.type == 'income', models.Transaction.created_at >= start_date_str).scalar() or 0
        expense = db.query(func.sum(models.Transaction.amount)).filter(models.Transaction.type == 'expense', models.Transaction.created_at >= start_date_str).scalar() or 0
        report_text = f"**گزارش مالی - {period_farsi}**\n\n🟢 **درآمد:** {income:,.0f} تومان\n🔴 **هزینه:** {expense:,.0f} تومان\n\n💰 **تراز:** {income - expense:,.0f} تومان"
        keyboard = [[InlineKeyboardButton(" بازگشت ⬅️", callback_data='report_menu')]]
        await query.edit_message_text(text=report_text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    finally: db.close()

# --- توابع ثبت تراکنش (ارتقا یافته) ---

async def handle_natural_language_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    db = next(get_db())
    try:
        parsed_data = parser.parse_transaction_text(update.message.text, db)
    finally:
        db.close()

    if parsed_data:
        context.user_data['pending_transaction'] = parsed_data

        # دریافت نام حساب و دسته‌بندی برای نمایش
        db = next(get_db())
        try:
            account_name = db.query(models.Account.name).filter(models.Account.id == parsed_data['account_id']).scalar() if parsed_data['account_id'] else "نامشخص"
            category_name = db.query(models.Category.name).filter(models.Category.id == parsed_data['category_id']).scalar() if parsed_data['category_id'] else "نامشخص"
        finally:
            db.close()

        amount_f = f"{parsed_data['amount']:,.0f}"
        type_f = "درآمد" if parsed_data['type'] == 'income' else "هزینه"

        reply_text = (
            f"🔍 **تراکنش شناسایی شد**\n\n"
            f"**نوع:** {type_f}\n"
            f"**مبلغ:** {amount_f} تومان\n"
            f"**شرح:** {parsed_data['description']}\n"
            f"**حساب:** {account_name}\n"
            f"**دسته‌بندی:** {category_name}\n\n"
            "آیا اطلاعات صحیح است؟"
        )
        await update.message.reply_text(
            reply_text,
            reply_markup=ReplyKeyboardMarkup([['بله', 'خیر']], one_time_keyboard=True, resize_keyboard=True),
            parse_mode='Markdown'
        )
        return CONFIRMATION

    await update.message.reply_text("متوجه نشدم. لطفاً تراکنش را واضح‌تر بیان کنید یا از منوی /start استفاده نمایید.")
    return ConversationHandler.END


async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text == 'بله':
        pending_data = context.user_data.get('pending_transaction')
        if not pending_data:
            await update.message.reply_text("خطا: اطلاعات تراکنش یافت نشد.", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END

        db = next(get_db())
        try:
            new_transaction = models.Transaction(
                amount=pending_data['amount'],
                type=pending_data['type'],
                description=pending_data['description'],
                account_id=pending_data['account_id'],
                category_id=pending_data['category_id'],
                transaction_date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                created_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            db.add(new_transaction)
            db.commit()
            await update.message.reply_text("✅ تراکنش با موفقیت ثبت شد.", reply_markup=ReplyKeyboardRemove())
        except Exception as e:
            db.rollback()
            logger.error(f"خطا در ثبت تراکنش: {e}")
            await update.message.reply_text("خطایی در ثبت تراکنش رخ داد.", reply_markup=ReplyKeyboardRemove())
        finally:
            db.close()
    else:
        await update.message.reply_text("عملیات لغو شد.", reply_markup=ReplyKeyboardRemove())

    context.user_data.pop('pending_transaction', None)
    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop('pending_transaction', None)
    await update.message.reply_text('عملیات لغو شد.', reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


def main() -> None:
    if not TELEGRAM_TOKEN: logger.error("توکن تلگرام تعریف نشده است."); return
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    allowed_filter = filters.User(user_id=ALLOWED_USER_IDS) if ALLOWED_USER_IDS else filters.ALL
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND & allowed_filter, handle_natural_language_message)],
        states={CONFIRMATION: [MessageHandler(filters.Regex('^(بله|خیر)$') & allowed_filter, handle_confirmation)]},
        fallbacks=[CommandHandler('cancel', cancel_conversation, filters=allowed_filter)],
        per_message=False
    )
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start, filters=allowed_filter))
    application.add_handler(CommandHandler("menu", start, filters=allowed_filter))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    logger.info("ربات آماده به کار است..."); application.run_polling()

if __name__ == "__main__":
    main()