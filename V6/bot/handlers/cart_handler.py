import logging
from decimal import Decimal
from telegram import Update, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters, CommandHandler
from telegram.error import BadRequest

from bot.utils import run_db
from db import crud
from bot import keyboards, responses
from config import ADMIN_USER_IDS

logger = logging.getLogger(__name__)

# وضعیت‌های Conversation
GET_ADDRESS, GET_PHONE, GET_RECEIPT = range(3)

# ==============================================================================
# Helper Function
# ==============================================================================
async def _safe_edit(update: Update, text: str, reply_markup: InlineKeyboardMarkup = None, parse_mode: str = 'HTML'):
    """
    سعی می‌کند پیام را ویرایش کند. اگر نشد (مثلاً پیام قبلی عکس بود)، حذف و ارسال می‌کند.
    """
    query = update.callback_query
    if not query:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        return

    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except BadRequest:
        # معمولاً وقتی رخ می‌دهد که پیام قبلی عکس باشد
        try:
            await query.message.delete()
            await query.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception as e:
            logger.error(f"Safe Edit Error: {e}")

# ==============================================================================
# Cart Management Handlers
# ==============================================================================

async def view_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نمایش سبد خرید"""
    user = update.effective_user
    query = update.callback_query
    
    if query: await query.answer()

    # اطمینان از وجود کاربر
    await run_db(crud.get_or_create_user, user.id, user.full_name or "کاربر")
    items = await run_db(crud.get_cart_items, user.id)

    if not items:
        # ارسال استیکر سبد خالی (اگر آیدی داشته باشد)
        if responses.STICKERS.get("sad"):
            try: await context.bot.send_sticker(user.id, responses.STICKERS["sad"])
            except: pass
            
        text = responses.CART_EMPTY
        kbd = keyboards.get_main_menu_keyboard()
        await _safe_edit(update, text, kbd)
        return

    # محاسبه مجموع
    items_total = sum(float(item.product.price) * item.quantity for item in items)
    
    text = f"{responses.CART_TITLE}{responses.get_divider()}"
    
    for idx, item in enumerate(items, 1):
        # اضافه کردن مشخصات (رنگ/سایز) به متن
        attr_text = f" ({item.selected_attributes})" if item.selected_attributes else ""
        item_price = float(item.product.price) * item.quantity
        
        text += responses.CART_ITEM_ROW.format(
            index=idx,
            name=f"<b>{item.product.name}{attr_text}</b>",
            quantity=item.quantity,
            total_formatted=responses.format_price(item_price)
        )
        
    text += responses.CART_TOTAL.format(total_amount_formatted=responses.format_price(items_total))
    
    kbd = keyboards.view_cart_keyboard(items)
    await _safe_edit(update, text, kbd)

async def add_to_cart_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """افزودن محصول به سبد خرید"""
    query = update.callback_query
    try:
        # data: cart:add:prod_id
        prod_id = int(query.data.split(':')[2])
        
        # افزودن به دیتابیس
        await run_db(crud.add_to_cart, query.from_user.id, prod_id, 1)
        
        # نمایش فیدبک
        prod = await run_db(crud.get_product, prod_id)
        await query.answer(f"✅ {prod.name} به سبد خرید اضافه شد.", show_alert=False)
        
        # رفرش صفحه محصول برای آپدیت تعداد
        from bot.handlers.products_handler import show_product_details
        await show_product_details(update, context)
        
    except ValueError as e:
        await query.answer(f"⚠️ موجودی کافی نیست!", show_alert=True)
    except Exception as e:
        logger.error(e)
        await query.answer("خطا در افزودن به سبد", show_alert=True)

async def update_cart_item_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تغییر تعداد آیتم در سبد خرید (+/-)"""
    query = update.callback_query
    # data: cart:upd:prod_id:change (+1 or -1)
    parts = query.data.split(':')
    prod_id = int(parts[2])
    change = int(parts[3])
    user_id = query.from_user.id

    # لاجیک آپدیت در دیتابیس
    def _update_logic(db, uid, pid, chg):
        from db import models
        items = db.query(models.CartItem).filter_by(user_id=uid, product_id=pid).all()
        if not items: return False, "آیتم یافت نشد"
        
        # آخرین آیتم اضافه شده را تغییر می‌دهیم
        item = items[-1]
        new_qty = item.quantity + chg
        
        if new_qty > 0:
            if chg > 0 and item.product.stock < new_qty:
                return False, "موجودی انبار کافی نیست"
            item.quantity = new_qty
        else:
            db.delete(item) # حذف اگر صفر شد
            
        db.commit()
        return True, "OK"

    success, msg = await run_db(_update_logic, user_id, prod_id, change)
    
    if not success:
        await query.answer(f"⚠️ {msg}", show_alert=True)
    else:
        await query.answer() # موفقیت آمیز
        await view_cart(update, context)

async def clear_cart_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """خالی کردن کل سبد خرید"""
    query = update.callback_query
    if query: await query.answer()
    
    # ارسال استیکر سطل زباله
    if responses.STICKERS.get("trash"):
        try: await context.bot.send_sticker(update.effective_chat.id, responses.STICKERS["trash"])
        except: pass
    
    await run_db(crud.clear_cart, update.effective_user.id)
    await view_cart(update, context)

# ==============================================================================
# Checkout Process (Conversation)
# ==============================================================================

async def start_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """شروع پروسه پرداخت"""
    query = update.callback_query
    await query.answer()

    # بررسی باز بودن فروشگاه
    is_open = await run_db(crud.get_setting, "shop_is_open", "true")
    if is_open == "false":
        await query.message.reply_text("⛔ فروشگاه در حال حاضر بسته است و امکان ثبت سفارش وجود ندارد.")
        return ConversationHandler.END

    # ارسال استیکر پرداخت
    if responses.STICKERS.get("checkout"):
        try: await context.bot.send_sticker(update.effective_chat.id, responses.STICKERS["checkout"])
        except: pass

    # بررسی آدرس‌های ذخیره شده
    addresses = await run_db(crud.get_user_addresses, query.from_user.id)
    
    if addresses:
        kbd = keyboards.get_address_book_keyboard(addresses, is_checkout=True)
        await query.message.reply_text(responses.get_checkout_address(has_saved_addr=True), reply_markup=kbd, parse_mode='HTML')
    else:
        await query.message.reply_text(responses.get_checkout_address(has_saved_addr=False), reply_markup=ReplyKeyboardRemove(), parse_mode='HTML')
        
    return GET_ADDRESS

async def handle_address_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """انتخاب آدرس از لیست ذخیره شده"""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("use_addr:"):
        addr_id = int(query.data.split(':')[1])
        
        def _get_addr(db, aid):
            from db.models import UserAddress
            addr = db.query(UserAddress).filter_by(id=aid).first()
            return addr.address_text if addr else None
            
        selected_addr = await run_db(_get_addr, addr_id)
        if selected_addr:
            context.user_data['address'] = selected_addr
            return await ask_phone_logic(query.message, context)
    
    # اگر دکمه آدرس جدید زده شد
    await query.message.reply_text("📍 لطفاً آدرس دقیق پستی خود را تایپ کنید:\n(استان، شهر، خیابان، پلاک، کد پستی)")
    return GET_ADDRESS

async def get_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """دریافت آدرس جدید متنی"""
    addr_text = update.message.text.strip()
    if len(addr_text) < 10:
        await update.message.reply_text("⚠️ آدرس خیلی کوتاه است. لطفاً دقیق‌تر وارد کنید:")
        return GET_ADDRESS
        
    context.user_data['address'] = addr_text
    
    # ذخیره آدرس در دفترچه آدرس
    await run_db(crud.add_user_address, update.effective_user.id, "آدرس جدید", addr_text)
    
    return await ask_phone_logic(update.message, context)

async def ask_phone_logic(message, context) -> int:
    """منطق مشترک درخواست شماره تلفن"""
    user = await run_db(crud.get_or_create_user, context._user_id, "")
    
    if user.phone_number:
        kbd = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"📞 استفاده از {user.phone_number}", callback_data="use_saved_phone")],
            [InlineKeyboardButton("✏️ شماره جدید", callback_data="new_phone")]
        ])
        await message.reply_text(f"📱 <b>شماره تماس جهت هماهنگی ارسال:</b>", reply_markup=kbd, parse_mode='HTML')
    else:
        await message.reply_text(
            responses.get_checkout_phone(), 
            reply_markup=keyboards.get_contact_keyboard(), 
            parse_mode='HTML'
        )
    return GET_PHONE

async def handle_phone_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """انتخاب شماره ذخیره شده"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "use_saved_phone":
        user = await run_db(crud.get_or_create_user, query.from_user.id, "")
        context.user_data['phone'] = user.phone_number
        return await show_invoice_logic(query.message, context)
        
    await query.message.reply_text("لطفاً شماره تماس خود را ارسال یا تایپ کنید:", reply_markup=keyboards.get_contact_keyboard())
    return GET_PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """دریافت شماره تماس جدید"""
    phone = update.message.contact.phone_number if update.message.contact else update.message.text.strip()
    
    # اعتبارسنجی ساده
    if not phone.isdigit() and not phone.startswith('+'):
        await update.message.reply_text("⚠️ فرمت شماره صحیح نیست. لطفاً مجدد ارسال کنید:")
        return GET_PHONE
        
    context.user_data['phone'] = phone
    
    # بروزرسانی شماره کاربر در دیتابیس
    await run_db(crud.update_user_phone, update.effective_user.id, phone)
    
    return await show_invoice_logic(update.message, context)

async def show_invoice_logic(message, context) -> int:
    """نمایش فاکتور نهایی و درخواست فیش"""
    user_id = context._user_id
    items = await run_db(crud.get_cart_items, user_id)
    
    if not items:
        await message.reply_text("سبد خرید شما خالی است.", reply_markup=keyboards.get_main_menu_keyboard())
        return ConversationHandler.END

    # محاسبه مبالغ
    items_total = sum(float(item.product.price) * item.quantity for item in items)
    
    ship_cost = float(await run_db(crud.get_setting, "shipping_cost", "0"))
    free_limit = float(await run_db(crud.get_setting, "free_shipping_limit", "0"))
    
    # محاسبه هزینه ارسال نهایی
    final_ship = 0 if (free_limit > 0 and items_total >= free_limit) else ship_cost
    final_total = items_total + final_ship
    
    # دریافت اطلاعات کارت
    card_num = await run_db(crud.get_setting, "card_number", "----")
    card_owner = await run_db(crud.get_setting, "card_owner", "")

    invoice_text = responses.get_checkout_payment(
        total=items_total,
        shipping_cost="رایگان" if final_ship == 0 else f"{final_ship:,.0f}",
        final_total=final_total,
        card_number=card_num,
        card_owner=card_owner
    )
    
    await message.reply_text(invoice_text, reply_markup=ReplyKeyboardRemove(), parse_mode='HTML')
    return GET_RECEIPT

async def get_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """دریافت عکس فیش و ثبت نهایی سفارش"""
    if not update.message.photo:
        await update.message.reply_text("⚠️ لطفاً عکس فیش واریزی را ارسال کنید (نه فایل).")
        return GET_RECEIPT

    user = update.effective_user
    photo_id = update.message.photo[-1].file_id
    
    shipping_data = {
        "address": context.user_data.get('address'),
        "phone": context.user_data.get('phone'),
        "postal_code": None # فعلا کد پستی جداگانه گرفته نمی‌شود
    }

    try:
        # ایجاد سفارش و پاک کردن سبد خرید (اتمیک در crud)
        order = await run_db(crud.create_order_from_cart, user.id, shipping_data)
        
        # ذخیره عکس فیش
        def _save_receipt(db, oid, pid):
            from db.models import Order
            o = db.query(Order).filter_by(id=oid).first()
            if o:
                o.payment_receipt_photo_id = pid
                db.commit()
        await run_db(_save_receipt, order.id, photo_id)

        # ارسال استیکر موفقیت
        if responses.STICKERS.get("success"):
            try: await context.bot.send_sticker(user.id, responses.STICKERS["success"])
            except: pass

        # پیام موفقیت به کاربر
        success_msg = responses.ORDER_CONFIRMATION.format(
            order_id=order.id, 
            divider=responses.get_divider(), 
            timeline="⏳ در انتظار بررسی"
        )
        await update.message.reply_text(success_msg, parse_mode='HTML')
        await update.message.reply_text("از خرید شما سپاسگزاریم! 🌹", reply_markup=keyboards.get_main_menu_keyboard())

        # اطلاع‌رسانی به ادمین‌ها
        admin_kb = keyboards.get_admin_order_keyboard(order.id, user.id)
        admin_caption = (
            f"🔔 <b>سفارش جدید #{order.id}</b>\n\n"
            f"👤 کاربر: {user.full_name} (@{user.username})\n"
            f"💰 مبلغ: {order.total_amount:,.0f} تومان\n"
            f"📱 تلفن: {shipping_data['phone']}\n"
            f"📍 آدرس: {shipping_data['address'][:100]}..."
        )
        
        for admin_id in ADMIN_USER_IDS:
            try: 
                await context.bot.send_photo(
                    chat_id=admin_id, 
                    photo=photo_id, 
                    caption=admin_caption, 
                    reply_markup=admin_kb,
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Failed to send to admin {admin_id}: {e}")

    except Exception as e:
        logger.error(f"Checkout Error: {e}")
        
        # استیکر خطا
        if responses.STICKERS.get("error"):
            try: await context.bot.send_sticker(user.id, responses.STICKERS["error"])
            except: pass
            
        await update.message.reply_text("❌ متاسفانه خطایی در ثبت سفارش رخ داد. ممکن است موجودی کالا تغییر کرده باشد.", reply_markup=keyboards.get_main_menu_keyboard())
    
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """لغو عملیات خرید"""
    await update.message.reply_text("❌ عملیات خرید لغو شد.", reply_markup=keyboards.get_main_menu_keyboard())
    context.user_data.clear()
    return ConversationHandler.END

# تعریف هندلر مکالمه
checkout_conversation_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_checkout, pattern=r'^cart:checkout$')],
    states={
        GET_ADDRESS: [
            CallbackQueryHandler(handle_address_choice, pattern=r"^(use_addr:|new_address)$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_address)
        ],
        GET_PHONE: [
            CallbackQueryHandler(handle_phone_choice, pattern=r"^(use_saved_phone|new_phone)$"),
            MessageHandler((filters.TEXT | filters.CONTACT) & ~filters.COMMAND, get_phone)
        ],
        GET_RECEIPT: [
            MessageHandler(filters.PHOTO, get_receipt)
        ],
    },
    fallbacks=[
        CommandHandler('cancel', cancel_checkout),
        CommandHandler('start', cancel_checkout), # بازگشت به منو
        CallbackQueryHandler(cancel_checkout, pattern="^main_menu$")
    ],
    per_chat=True, 
    per_user=True,
)