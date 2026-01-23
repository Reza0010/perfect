import asyncio
import threading
import traceback
import contextvars
from typing import Any, Callable, Optional, Generator, Union

from PyQt6.QtCore import QObject, QThread, pyqtSignal

class AsyncWorker(QObject):
    """
    کارگر غیرهمگام (Async Worker) پیشرفته و ایمن برای PyQt6.
    
    ویژگی‌ها:
    - اجرای توابع async در ترد جداگانه بدون فریز شدن UI.
    - مدیریت خودکار EventLoop و Thread Lifecycle.
    - پشتیبانی از ContextVars (برای سازگاری با SQLAlchemy و ابزارهای مدرن).
    - پشتیبانی از Progress (برای توابع طولانی یا دانلود).
    """
    
    # سیگنال‌ها
    started = pyqtSignal()
    finished = pyqtSignal(object)      # بازگشت نتیجه نهایی
    progress = pyqtSignal(object)      # گزارش پیشرفت (عدد، متن، یا تاپل)
    error = pyqtSignal(object)         # ارسال خطا (می‌تواند Exception یا string باشد)
    cancelled = pyqtSignal()

    def __init__(self, async_func: Callable, *args: Any, **kwargs: Any):
        super().__init__()
        self.async_func = async_func
        self.args = args
        self.kwargs = kwargs
        
        # کپی کردن کانتکست فعلی (مهم برای دیتابیس و لاگینگ در ترد جدید)
        self.context = contextvars.copy_context()
        
        # داخلی
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._task: Optional[asyncio.Task] = None
        self._is_cancelled = False
        self._thread: Optional[QThread] = None
        self._lock = threading.Lock()

    def run(self) -> None:
        """
        نقطه ورود اجرا (در ترد جدید فراخوانی می‌شود).
        """
        if self.check_cancelled():
            return

        self.started.emit()

        try:
            # ایجاد لوپ جدید برای این ترد
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            # اجرای تابع در کانتکست صحیح
            # این کار باعث می‌شود متغیرهای ContextVar (مثل سشن دیتابیس) درست کار کنند
            self._task = self._loop.create_task(
                self.async_func(*self.args, **self.kwargs),
                name="AsyncWorkerTask"
            )
            
            # اجرای تسک
            # اگر تابع یک Async Generator باشد (یعنی yield داشته باشد)، آن را مصرف می‌کنیم
            # این برای گزارش Progress عالی است
            if asyncio.iscoroutinefunction(self.async_func):
                result = self._loop.run_until_complete(self._task)
                
                # اگر نتیجه نهایی یک جنراتور ناهمگام بود (ندرتاً پیش می‌آید ولی محکم کاری)
                if hasattr(result, '__aiter__'):
                     self._loop.run_until_complete(self._consume_generator(result))
                     result = None # جنراتورها معمولاً مقدار بازگشتی نهایی ندارند
            else:
                # اگر تابع معمولی async است
                result = self._loop.run_until_complete(self._task)

            if not self.check_cancelled():
                self.finished.emit(result)

        except asyncio.CancelledError:
            if not self._is_cancelled:
                # کنسل شدن غیرمنتظره
                self.error.emit(asyncio.CancelledError("Operation stopped unexpectedly."))
            else:
                self.cancelled.emit()

        except Exception as e:
            if not self.check_cancelled():
                # چاپ کامل خطا در کنسول برای دولوپر
                traceback.print_exc()
                # ارسال خطا به UI
                self.error.emit(e)

        finally:
            self._cleanup()

    async def _consume_generator(self, agen):
        """مصرف کننده جنراتور ناهمگام برای گزارش پیشرفت"""
        async for item in agen:
            if self._is_cancelled:
                break
            # ارسال هر آیتم yield شده به عنوان سیگنال پیشرفت
            self.progress.emit(item)

    def auto_start(self, thread_name: str = "AsyncWorkerThread"):
        """
        راه‌اندازی خودکار: ساخت ترد، انتقال ورکر، و استارت.
        این بهترین روش برای استفاده در UI است.
        """
        self._thread = QThread()
        self._thread.setObjectName(thread_name)
        self.moveToThread(self._thread)
        
        self._thread.started.connect(self.run)
        
        # پاکسازی پس از پایان
        # (استفاده از ConnectionType.QueuedConnection برای اطمینان از ترد سیف بودن)
        self.finished.connect(self._stop_thread, Qt.ConnectionType.QueuedConnection)
        self.error.connect(self._stop_thread, Qt.ConnectionType.QueuedConnection)
        self.cancelled.connect(self._stop_thread, Qt.ConnectionType.QueuedConnection)
        
        self._thread.start()

    def cancel(self) -> None:
        """درخواست لغو عملیات (Thread-Safe)"""
        with self._lock:
            self._is_cancelled = True

        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._cancel_task)

    def _cancel_task(self):
        if self._task and not self._task.done():
            self._task.cancel()

    def check_cancelled(self) -> bool:
        with self._lock:
            if self._is_cancelled:
                self.cancelled.emit()
                return True
        return False

    def _cleanup(self):
        """بستن لوپ و آزاد کردن منابع"""
        try:
            if self._loop and not self._loop.is_closed():
                # کنسل کردن همه تسک‌های باقیمانده
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                
                # دادن زمان کوتاه برای پاکسازی
                if pending:
                    self._loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
                
                self._loop.close()
        except Exception as e:
            print(f"AsyncWorker Cleanup Error: {e}")
        finally:
            self._loop = None
            self._task = None

    def _stop_thread(self):
        """توقف و حذف ترد"""
        if self._thread:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
            self.deleteLater()

# ==============================================================================
# Helper Function (برای استفاده راحت‌تر)
# ==============================================================================
def run_async(func: Callable, *args, on_success=None, on_error=None, on_progress=None, **kwargs):
    """
    یک تابع کمکی (Helper) برای اجرای سریع یک تسک ناهمگام بدون درگیر شدن با کلاس Worker.
    
    مثال:
        run_async(my_async_func, arg1, on_success=print, on_error=show_error)
    """
    worker = AsyncWorker(func, *args, **kwargs)
    
    if on_success:
        worker.finished.connect(on_success)
    if on_error:
        worker.error.connect(on_error)
    if on_progress:
        worker.progress.connect(on_progress)
        
    worker.auto_start()
    return worker # بازگرداندن ورکر برای دسترسی به متد cancel در صورت نیاز