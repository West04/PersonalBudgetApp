from fastapi import FastAPI

from .routers import categories, budgets, transactions, plaid


app = FastAPI()

app.include_router(categories.router)
app.include_router(budgets.router)
app.include_router(transactions.router)
app.include_router(plaid.router)