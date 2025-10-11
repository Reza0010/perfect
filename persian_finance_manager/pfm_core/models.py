from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime, Enum
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.sql import func
import os

# مسیر پایگاه داده
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'finance.db'))
DATABASE_URL = f"sqlite:///{DB_PATH}"

# ایجاد موتور پایگاه داده
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# ایجاد یک SessionLocal class برای مدیریت session های پایگاه داده
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class برای مدل‌های ما
Base = declarative_base()


# --- تعریف مدل‌ها ---

class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)

    transactions = relationship("Transaction", back_populates="account")

class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)

    transactions = relationship("Transaction", back_populates="category")

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    amount = Column(Float, nullable=False)
    type = Column(Enum('income', 'expense', name='transaction_type'), nullable=False)
    description = Column(String)
    transaction_date = Column(String, nullable=False) # برای سادگی فعلا از رشته استفاده می‌کنیم
    created_at = Column(String, nullable=False, default=func.now())

    account_id = Column(Integer, ForeignKey("accounts.id"))
    category_id = Column(Integer, ForeignKey("categories.id"))

    account = relationship("Account", back_populates="transactions")
    category = relationship("Category", back_populates="transactions")

def get_db():
    """
    یک Dependency برای FastAPI که یک session پایگاه داده را فراهم می‌کند.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# این تابع دیگر مستقیماً استفاده نمی‌شود، اما برای مرجع نگه داشته می‌شود.
# ایجاد جداول به صورت دستی یا با ابزارهای migration (مانند Alembic) انجام می‌شود.
# ما قبلاً جداول را با database.py ایجاد کرده‌ایم.
def create_all_tables():
    Base.metadata.create_all(bind=engine)