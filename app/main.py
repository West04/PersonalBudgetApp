from fastapi import FastAPI

from .routers import categories, budgets, transactions


app = FastAPI()

app.include_router(categories.router)
app.include_router(budgets.router)
app.include_router(transactions.router)