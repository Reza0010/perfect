import sys
import os
import csv
import io
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from pydantic import BaseModel
from typing import List, Optional, Dict

# افزودن مسیر ریشه پروژه به sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pfm_core import models
from pfm_core.models import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Pydantic Models ---
class CategoryExpense(BaseModel):
    category_name: str
    total_amount: float

class DashboardData(BaseModel):
    total_income: float
    total_expense: float
    balance: float
    category_expenses: List[CategoryExpense]

# --- API Endpoints ---
@app.get("/api/dashboard-data", response_model=DashboardData)
def get_dashboard_data(db: Session = Depends(get_db)):
    thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    total_income = db.query(func.sum(models.Transaction.amount)).filter(models.Transaction.type == 'income', models.Transaction.created_at >= thirty_days_ago).scalar() or 0.0
    total_expense = db.query(func.sum(models.Transaction.amount)).filter(models.Transaction.type == 'expense', models.Transaction.created_at >= thirty_days_ago).scalar() or 0.0
    category_expenses_query = db.query(models.Category.name, func.sum(models.Transaction.amount).label("total_amount")).join(models.Transaction).filter(models.Transaction.type == 'expense', models.Transaction.created_at >= thirty_days_ago).group_by(models.Category.name).order_by(func.sum(models.Transaction.amount).desc()).all()
    category_expenses = [CategoryExpense(category_name=name, total_amount=total) for name, total in category_expenses_query]
    return DashboardData(total_income=total_income, total_expense=total_expense, balance=total_income - total_expense, category_expenses=category_expenses)

def _get_filtered_transactions_query(db: Session, q: Optional[str], type: Optional[str], account_id: Optional[int], category_id: Optional[int]):
    query = db.query(models.Transaction).outerjoin(models.Account).outerjoin(models.Category)
    if q: query = query.filter(models.Transaction.description.ilike(f"%{q}%"))
    if type: query = query.filter(models.Transaction.type == type)
    if account_id: query = query.filter(models.Transaction.account_id == account_id)
    if category_id: query = query.filter(models.Transaction.category_id == category_id)
    return query.order_by(models.Transaction.id.desc())

@app.get("/api/transactions")
def get_transactions(db: Session = Depends(get_db), q: Optional[str] = None, type: Optional[str] = None, account_id: Optional[int] = None, category_id: Optional[int] = None):
    transactions = _get_filtered_transactions_query(db, q, type, account_id, category_id).all()
    results = []
    for t in transactions:
        results.append({
            "id": t.id, "type": t.type, "amount": t.amount, "description": t.description,
            "transaction_date": t.transaction_date, "account_name": t.account.name if t.account else "ندارد",
            "category_name": t.category.name if t.category else "ندارد"
        })
    return results

@app.get("/api/export-csv")
def export_csv(db: Session = Depends(get_db), q: Optional[str] = None, type: Optional[str] = None, account_id: Optional[int] = None, category_id: Optional[int] = None):
    transactions = _get_filtered_transactions_query(db, q, type, account_id, category_id).all()

    output = io.StringIO()
    writer = csv.writer(output)

    # نوشتن هدر فایل CSV
    writer.writerow(["ID", "Type", "Amount", "Description", "Account", "Category", "Date"])

    for t in transactions:
        writer.writerow([
            t.id, t.type, t.amount, t.description,
            t.account.name if t.account else "",
            t.category.name if t.category else "",
            t.transaction_date
        ])

    output.seek(0)
    return StreamingResponse(output, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=transactions_{datetime.now().strftime('%Y%m%d')}.csv"})

# --- HTML & Form Endpoints (بدون تغییر) ---
@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/transactions")
async def list_transactions_page(request: Request, db: Session = Depends(get_db)):
    accounts = db.query(models.Account).all()
    categories = db.query(models.Category).all()
    return templates.TemplateResponse("transactions.html", {"request": request, "accounts": accounts, "categories": categories})

@app.get("/management")
async def management_page(request: Request, db: Session = Depends(get_db)):
    categories = db.query(models.Category).all()
    accounts = db.query(models.Account).all()
    return templates.TemplateResponse("management.html", {"request": request, "categories": categories, "accounts": accounts})

@app.post("/add_category")
async def add_category(name: str = Form(...), db: Session = Depends(get_db)):
    db.add(models.Category(name=name)); db.commit()
    return RedirectResponse(url="/management", status_code=303)

@app.post("/add_account")
async def add_account(name: str = Form(...), db: Session = Depends(get_db)):
    db.add(models.Account(name=name)); db.commit()
    return RedirectResponse(url="/management", status_code=303)

@app.post("/delete_category/{category_id}")
async def delete_category(category_id: int, db: Session = Depends(get_db)):
    category = db.get(models.Category, category_id)
    if not category: raise HTTPException(404, "Category not found")
    db.delete(category); db.commit()
    return RedirectResponse(url="/management", status_code=303)

@app.post("/delete_account/{account_id}")
async def delete_account(account_id: int, db: Session = Depends(get_db)):
    account = db.get(models.Account, account_id)
    if not account: raise HTTPException(404, "Account not found")
    db.delete(account); db.commit()
    return RedirectResponse(url="/management", status_code=303)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)