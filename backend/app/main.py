"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: startup and shutdown events."""
    settings = get_settings()
    # Startup
    print(f"Starting {settings.app_name} ({settings.app_env})")
    yield
    # Shutdown
    print(f"Shutting down {settings.app_name}")


def create_app() -> FastAPI:
    """Application factory — creates and configures the FastAPI instance."""
    settings = get_settings()

    application = FastAPI(
        title="AI Codebase Architecture & Onboarding Analyzer",
        description="Automated codebase analysis, architecture visualization, and onboarding docs.",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # ── CORS Middleware ──────────────────────────────────────
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.backend_cors_origins,
        allow_origin_regex=r"^https:\/\/.*\.vercel\.app$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── API Router ───────────────────────────────────────────
    application.include_router(api_router)

    # ── Health Check ─────────────────────────────────────────
    @application.get("/healthz", tags=["health"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/api/v1/ping", tags=["health"])
    async def ping() -> dict[str, str]:
        return {"message": "pong", "environment": settings.app_env}

    return application


app = create_app()
