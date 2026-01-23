import asyncio
import logging
import traceback
from typing import Callable, Any, TypeVar

from db.database import SessionLocal

logger = logging.getLogger(__name__)

# تعریف TypeVar برای حفظ تایپ خروجی تابع اصلی
T = TypeVar("T")

async def run_db(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """
    اجرای توابع دیتابیس (همگام/Sync) در یک ترد جداگانه (غیرهمگام/Async).
    
    این تابع باعث می‌شود عملیات سنگین دیتابیس، Event Loop اصلی ربات تلگرام را
    مسدود نکنند و ربات حتی هنگام پردازش‌های سنگین هم پاسخگو بماند.

    :param func: تابع لایه CRUD که باید اجرا شود (اولین پارامترش باید db باشد).
    :param args: آرگومان‌های موقعیتی تابع.
    :param kwargs: آرگومان‌های نام‌دار تابع.
    :return: خروجی تابع صدا زده شده.
    """
    def wrapper():
        # ایجاد یک سشن اختصاصی برای این ترد
        # استفاده از Context Manager باعث می‌شود سشن در هر صورت (موفق یا خطا) بسته شود
        with SessionLocal() as db:
            try:
                # اجرای تابع مورد نظر و پاس دادن دیتابیس به عنوان آرگومان اول
                return func(db, *args, **kwargs)
            except Exception as e:
                # ثبت خطای دقیق به همراه Traceback برای دیباگ
                logger.error(f"❌ Database Critical Error in '{func.__name__}': {e}")
                logger.debug(traceback.format_exc())
                
                # پرتاب مجدد خطا تا فراخوان‌کننده (مثلاً هندلر بات) بتواند به کاربر پیام خطا دهد
                raise e

    # استفاده از asyncio.to_thread (بهترین روش در پایتون 3.9+ برای اجرای کد Blocking)
    return await asyncio.to_thread(wrapper)