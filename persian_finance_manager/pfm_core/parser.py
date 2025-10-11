import re
from typing import Dict, Optional, Tuple, List
from . import models  # Use relative import

def _convert_persian_to_english_numbers(text: str) -> str:
    persian_arabic_map = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
    return text.translate(persian_arabic_map)

def _find_keywords_in_text(text: str, keywords: List[models.Base]) -> Optional[int]:
    """
    در متن به دنبال لیستی از کلمات کلیدی (مدل‌های SQLAlchemy) می‌گردد و ID اولین مورد پیدا شده را برمی‌گرداند.
    """
    for item in keywords:
        if item.name in text:
            return item.id
    return None

# --- توابع استخراج مبلغ (بدون تغییر) ---
def _extract_structured_amount(text: str) -> Optional[Tuple[float, str]]:
    pattern = re.compile(r"مبلغ\s*:\s*([\d,]+)\s*(ریال)?")
    match = pattern.search(text)
    if match:
        amount_str, currency = match.groups()
        amount = float(amount_str.replace(",", ""))
        if currency == "ریال":
            amount /= 10
        return amount, match.group(0)
    return None

def _extract_conversational_amount(text: str) -> Optional[Tuple[float, str]]:
    pattern = re.compile(r"([\d\.]+)\s*(هزار|میلیون|میلیارد)?")
    match = pattern.search(text)
    if not match: return None
    value_str, multiplier_word = match.groups()
    try: amount = float(value_str)
    except ValueError: return None
    multipliers = {"هزار": 1000, "میلیون": 1_000_000, "میلیارد": 1_000_000_000}
    if multiplier_word in multipliers: amount *= multipliers[multiplier_word]
    return amount, match.group(0)

# --- تابع اصلی تحلیلگر (بازنویسی شده) ---
def parse_transaction_text(text: str, db_session) -> Optional[Dict]:
    """
    یک پیام متنی فارسی را تحلیل می‌کند و جزئیات تراکنش، از جمله حساب و دسته‌بندی را استخراج می‌کند.
    """
    if not text: return None

    # 1. خواندن دسته‌بندی‌ها و حساب‌ها از پایگاه داده
    categories = db_session.query(models.Category).all()
    accounts = db_session.query(models.Account).all()

    original_text = text
    processed_text = _convert_persian_to_english_numbers(original_text)

    amount = None
    amount_str_to_remove = ""
    remaining_text = processed_text

    # 2. استخراج مبلغ (با همان منطق قبلی)
    structured_result = _extract_structured_amount(processed_text)
    if structured_result:
        amount, amount_str_to_remove = structured_result
        trans_type = 'expense'
    else:
        conversational_result = _extract_conversational_amount(processed_text)
        if conversational_result:
            amount, amount_str_to_remove = conversational_result
            income_keywords = ["واریز", "دریافت", "حقوق", "شارژ حساب"]
            trans_type = 'income' if any(kw in processed_text for kw in income_keywords) else 'expense'
        else:
            return None

    if amount_str_to_remove:
        remaining_text = processed_text.replace(amount_str_to_remove, "", 1)

    # 3. استخراج حساب و دسته‌بندی
    account_id = _find_keywords_in_text(remaining_text, accounts)
    category_id = _find_keywords_in_text(remaining_text, categories)

    # 4. استخراج شرح (با کمی بهبود)
    keywords_to_remove = [
        "واریز", "دریافت", "حقوق", "خرید", "پرداخت", "هزینه", "برداشت", "خرج",
        "بابت", "برای", "تومان", "تومن", "ریال", "از", "به", "تراکنش موفق"
    ] + [item.name for item in categories] + [item.name for item in accounts]

    description = remaining_text
    for keyword in keywords_to_remove:
        description = description.replace(keyword, "")

    description = re.sub(r'\s+', ' ', description).strip()
    description = description or "تراکنش نامشخص"

    return {
        "amount": amount,
        "type": trans_type,
        "description": description,
        "account_id": account_id,
        "category_id": category_id,
        "original_text": original_text
    }