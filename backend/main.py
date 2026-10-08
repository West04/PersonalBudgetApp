from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import (
    engine,
    SessionLocal,
    migrate_review_state,
    migrate_reconciliation_state,
    migrate_merchant_state,
    migrate_categorization_rules,
    migrate_ml_state,
    migrate_recurring_state,
    migrate_split_state,
    migrate_budget_category_integrity,
    migrate_transaction_description_integrity,
    migrate_plaid_token_encryption,
)
from . import models
from .routers import categories, budgets, transactions, plaid, summaries, accounts, upload, credit_cards, rules, ml, recurring
from .initial_data import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    models.Base.metadata.create_all(bind=engine)
    migrate_review_state(engine)
    migrate_reconciliation_state(engine)
    migrate_merchant_state(engine)
    migrate_categorization_rules(engine)
    migrate_ml_state(engine)
    migrate_recurring_state(engine)
    migrate_split_state(engine)
    migrate_budget_category_integrity(engine)
    migrate_transaction_description_integrity(engine)
    migrate_plaid_token_encryption(engine)
    
    # Initialize default data
    db = SessionLocal()
    try:
        init_db(db)
    finally:
        db.close()
    
    yield


app = FastAPI(lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:12345"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(categories.router)
app.include_router(budgets.router)
app.include_router(transactions.router)
app.include_router(plaid.router)
app.include_router(summaries.router)
app.include_router(accounts.router)
app.include_router(upload.router)
app.include_router(credit_cards.router)
app.include_router(rules.router)
app.include_router(ml.router)
app.include_router(recurring.router)


