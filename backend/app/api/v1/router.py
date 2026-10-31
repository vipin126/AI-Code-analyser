"""API v1 router — aggregates all endpoint routers."""

from fastapi import APIRouter

from app.api.v1.endpoints import analysis, chat, repositories

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(
    repositories.router,
    prefix="/repositories",
    tags=["repositories"],
)
api_router.include_router(
    analysis.router,
    prefix="/repositories",
    tags=["analysis"],
)
api_router.include_router(
    chat.router,
    prefix="/repositories",
    tags=["chat"],
)
