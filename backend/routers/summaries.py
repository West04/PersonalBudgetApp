from fastapi import APIRouter

router = APIRouter(
    prefix="/summaries",
    tags=["Summaries"],
)