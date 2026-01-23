import math
import logging
import asyncio
from pathlib import Path
from typing import List

from telegram import Update, constants, InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest

from bot.utils import run_db
from db import crud, models
from bot import keyboards, responses
from config import BASE_DIR

logger = logging.getLogger(__name__)
PRODUCTS_PER_PAGE = 6

# ==============================================================================
# توابع کمکی (Helpers)
# ==============================================================================

async def build_breadcrumb(cat_id: int) -> str:
    """
    ساخت نوار ناوبری (Breadcrumb) به صورت بازگشتی.
    مثال خروجی: 🏠 خانه > 👔 پوشاک > 👞 کفش
    """
    path_names = []
    current_id = cat_id

    # حلقه برای پیدا کردن والدین تا رسیدن به ریشه
    while current_id:
        # دریافت نام و والد دسته جاری
        def get_cat_info(db, cid):
            c = db.query(models.Category).filter_by(id=cid).first()
            return (c.name, c.parent_id) if c else None
        
        cat_info = await run_db(get_cat_info, current_id)
        
        if cat_info:
            name, parent_id = cat_info
            path_names.append(name)
            current_id = parent_id
        else:
            break
            
    # معکوس کردن لیست (چون از فرزند به والد رفتیم)
    path_names.reverse()
    
    # ساخت رشته نهایی
    breadcrumb_str = "🏠 <b>خانه</b>"
    if path_names:
        breadcrumb_str += " > " + " > ".join(f"<b>{n}</b>" for n in path_names)
        
    return breadcrumb_str

# ==============================================================================
# هندلرهای اصلی (Handlers)
# ==============================================================================

async def list_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نمایش لیست دسته‌بندی‌ها (اصلی یا زیرمجموعه)"""
    query = update.callback_query
    await query.answer()

    parent_id = None
    # بررسی اینکه آیا درخواست برای زیرمجموعه است یا ریشه
    if query.data.startswith("cat:list:") and len(query.data.split(':')) > 2:
        try:
            val = query.data.split(':')[2]
            # اگر مقدار 'None' یا خالی نبود، تبدیل به int کن
            if val and val != 'None':
                parent_id = int(val)
        except ValueError: 
            pass

    # دریافت دسته‌ها
    if parent_id:
        categories = await run_db(crud.get_subcategories, parent_id)
    else:
        categories = await run_db(crud.get_root_categories)

    # اگر این دسته زیرمجموعه‌ای نداشت، یعنی کاربر باید محصولاتش را ببیند
    if not categories and parent_id:
        await render_products_page(update, context, cat_id=parent_id, page=1)
        return

    # ساخت کیبورد و متن
    kbd = keyboards.build_category_keyboard(categories, parent_id)
    
    # ساخت نوار ناوبری برای بالای لیست دسته‌ها
    if parent_id:
        breadcrumb = await build_breadcrumb(parent_id)
        text = f"{breadcrumb}\n\n{responses.CATEGORY_SELECT}"
    else:
        text = f"🏠 <b>منوی دسته‌بندی‌ها</b>\n\n{responses.CATEGORY_SELECT}"

    if not categories and not parent_id:
        text = "📂 هنوز دسته‌بندی‌ای تعریف نشده است."

    try:
        await query.edit_message_text(text, reply_markup=kbd, parse_mode='HTML')
    except BadRequest:
        await query.message.delete()
        await query.message.reply_text(text, reply_markup=kbd, parse_mode='HTML')

async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """هندلر دکمه‌های صفحه‌بندی محصولات"""
    query = update.callback_query
    
    if query.data == "noop":
        await query.answer()
        return

    await query.answer()
    try:
        # data format: prod:list:cat_id:page
        parts = query.data.split(':')
        cat_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 1
        
        await render_products_page(update, context, cat_id, page)
    except (IndexError, ValueError) as e:
        logger.error(f"List products error: {e}")

async def render_products_page(update: Update, context: ContextTypes.DEFAULT_TYPE, cat_id: int, page: int):
    """تابع مرکزی نمایش لیست محصولات با نوار ناوبری"""
    query = update.callback_query
    
    # 1. دریافت محصولات فعال
    all_prods = await run_db(crud.get_active_products_by_category, cat_id)
    
    # 2. لاجیک صفحه‌بندی
    total_items = len(all_prods)
    total_pages = max(1, math.ceil(total_items / PRODUCTS_PER_PAGE))
    
    if page > total_pages: page = total_pages
    if page < 1: page = 1
    
    start = (page - 1) * PRODUCTS_PER_PAGE
    end = start + PRODUCTS_PER_PAGE
    prods = all_prods[start:end]
    
    # 3. ساخت نوار ناوبری (Breadcrumb)
    breadcrumb = await build_breadcrumb(cat_id)

    # 4. ساخت کیبورد و متن
    kbd = keyboards.build_product_keyboard(prods, cat_id, page, total_pages)
    
    # استفاده از کلید breadcrumbs که در responses.py تعریف کردیم
    try:
        text = responses.PRODUCT_LIST.format(breadcrumbs=breadcrumb)
    except KeyError:
        # فال‌بک در صورتی که فایل responses هنوز آپدیت نشده باشد
        text = f"{breadcrumb}\n\n👇 محصولات موجود:"
    
    if not prods:
        text = f"{breadcrumb}\n\n❌ محصولی در این دسته موجود نیست."

    try:
        await query.edit_message_text(text, reply_markup=kbd, parse_mode='HTML')
    except BadRequest:
        await query.message.delete()
        await query.message.reply_text(text, reply_markup=kbd, parse_mode='HTML')

async def show_product_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نمایش جزئیات کامل محصول"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    try:
        if query: 
            await query.answer()
            data = query.data
            msg_obj = query.message
        else:
            args = context.args[0] if context.args else ""
            data = f"prod:show:{args.replace('p_', '')}"
            msg_obj = update.message

        prod_id = int(data.split(':')[2])
    except (IndexError, ValueError, AttributeError): 
        return

    # دریافت محصول از دیتابیس
    prod = await run_db(crud.get_product, prod_id)
    if not prod:
        if query: await query.edit_message_text("❌ محصول یافت نشد.")
        else: await msg_obj.reply_text("❌ محصول یافت نشد.")
        return

    # دریافت اطلاعات تکمیلی
    cart_items = await run_db(crud.get_cart_items, user_id)
    favs = await run_db(crud.get_user_favorites, user_id)
    is_fav = any(p.id == prod_id for p in favs)
    
    bot_info = await context.bot.get_me()

    # تعداد در سبد خرید
    this_item = next((i for i in cart_items if i.product_id == prod.id), None)
    cart_qty = this_item.quantity if this_item else 0
    
    # متن‌ها
    stock_status_text = f"✅ موجود ({prod.stock} عدد)" if prod.stock > 0 else "❌ ناموجود"
    cart_preview_text = f"\n🛒 <b>تعداد در سبد شما: {cart_qty}</b>" if cart_qty > 0 else ""
    
    final_price = prod.discount_price if prod.discount_price and prod.discount_price > 0 else prod.price
    price_text = responses.format_price(final_price)
    if prod.discount_price and prod.discount_price > 0:
        price_text = f"<s>{responses.format_price(prod.price)}</s> ➡️ <b>{responses.format_price(final_price)}</b> 🔥"

    try:
        text = responses.PRODUCT_DETAILS.format(
            name=prod.name,
            divider=responses.get_divider(),
            description=prod.description or "توضیحات ندارد",
            brand=prod.brand or "متفرقه",
            stock_status=stock_status_text,
            price_formatted=price_text,
            cart_preview=cart_preview_text
        )
    except KeyError:
        text = f"<b>{prod.name}</b>\n\n{prod.description}\n\n💰 {price_text}"

    kbd = keyboards.get_product_detail_keyboard(prod, is_fav, cart_qty, bot_info.username)

    # --- ارسال تصویر (هوشمند) ---
    async def send_with_local_image():
        if prod.image_path:
            full_path = Path(BASE_DIR) / prod.image_path
            if full_path.exists():
                with open(full_path, 'rb') as f:
                    sent = await context.bot.send_photo(
                        msg_obj.chat_id, f, caption=text, reply_markup=kbd, parse_mode='HTML'
                    )
                    await run_db(crud.update_product, prod.id, image_file_id=sent.photo[-1].file_id)
                return True
        return False

    # 1. تلاش با File ID
    if prod.image_file_id:
        try:
            if msg_obj.photo:
                await msg_obj.edit_media(
                    media=InputMediaPhoto(media=prod.image_file_id, caption=text, parse_mode='HTML'),
                    reply_markup=kbd
                )
            else:
                await msg_obj.delete()
                await context.bot.send_photo(msg_obj.chat_id, prod.image_file_id, caption=text, reply_markup=kbd, parse_mode='HTML')
            return
        except BadRequest:
            await run_db(crud.update_product, prod.id, image_file_id=None)

    # 2. تلاش با فایل محلی
    try:
        if await send_with_local_image():
            if msg_obj and not msg_obj.photo: await msg_obj.delete()
            return
    except Exception:
        pass

    # 3. بدون عکس
    try:
        if msg_obj.text:
            await msg_obj.edit_text(text, reply_markup=kbd, parse_mode='HTML')
        else:
            await msg_obj.delete()
            await context.bot.send_message(msg_obj.chat_id, text, reply_markup=kbd, parse_mode='HTML')
    except BadRequest:
        await msg_obj.reply_text(text, reply_markup=kbd, parse_mode='HTML')

async def toggle_favorite_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        prod_id = int(query.data.split(':')[2])
        is_fav = await run_db(crud.toggle_favorite, update.effective_user.id, prod_id)
        msg = "❤️ به علاقه‌مندی‌ها اضافه شد" if is_fav else "💔 از علاقه‌مندی‌ها حذف شد"
        await query.answer(msg)
        await show_product_details(update, context)
    except Exception:
        await query.answer("خطا", show_alert=True)

async def show_favorites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    favs = await run_db(crud.get_user_favorites, update.effective_user.id)
    
    if not favs:
        await query.message.reply_text("💔 لیست علاقه‌مندی‌های شما خالی است.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بازگشت", callback_data="main_menu")]]))
        return

    btns = [[InlineKeyboardButton(f"❤️ {p.name}", callback_data=f"prod:show:{p.id}")] for p in favs]
    btns.append([InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")])
    await query.message.reply_text("❤️ <b>علاقه‌مندی‌های شما:</b>", reply_markup=InlineKeyboardMarkup(btns), parse_mode='HTML')

async def notify_me_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    prod_id = int(query.data.split(':')[1])
    await run_db(crud.add_product_notification, update.effective_user.id, prod_id)
    await query.answer("✅ ثبت شد!", show_alert=True)

async def start_attribute_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prod_id = int(query.data.split(':')[2])
    prod = await run_db(crud.get_product, prod_id)
    
    if not prod: return

    if prod.variants:
        btns = []
        for v in prod.variants:
            if v.stock > 0:
                label = f"{v.name} ({int(prod.price + v.price_adjustment):,} ت)"
                btns.append([InlineKeyboardButton(label, callback_data=f"attr:sel:{prod.id}:{v.id}")])
        btns.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"prod:show:{prod.id}")])
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(btns))
    
    elif prod.attributes:
        attrs = [x.strip() for x in prod.attributes.replace('،', ',').split(',') if x.strip()]
        btns = [[InlineKeyboardButton(f"🔹 {a}", callback_data=f"attr:sel:{prod.id}:{a}")] for a in attrs]
        btns.append([InlineKeyboardButton("🔙 بازگشت", callback_data=f"prod:show:{prod.id}")])
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(btns))
    
    else:
        await run_db(crud.add_to_cart, query.from_user.id, prod.id, 1)
        await query.answer("✅ به سبد خرید اضافه شد.", show_alert=True)
        await show_product_details(update, context)

async def confirm_attribute_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split(':')
    prod_id = int(parts[2])
    selected_val = parts[3]
    
    await run_db(crud.add_to_cart, query.from_user.id, prod_id, 1, attributes=str(selected_val))
    await query.answer(f"✅ مدل '{selected_val}' اضافه شد.", show_alert=True)
    await show_product_details(update, context)