from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import engine, SessionLocal, migrate_review_state
from . import models
from .routers import categories, budgets, transactions, plaid, summaries, accounts, upload, credit_cards
from .initial_data import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    models.Base.metadata.create_all(bind=engine)
    migrate_review_state(engine)
    
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
