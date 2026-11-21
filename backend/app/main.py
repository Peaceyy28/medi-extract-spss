"""FastAPI application entry point for MediExtract SPSS."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.exports import router as exports_router
from app.api.health import router as health_router
from app.api.merge import router as merge_router
from app.api.projects import router as projects_router
from app.api.transforms import router as transforms_router
from app.config import get_settings


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title="MediExtract SPSS API",
        version=settings.schema_version,
        description=(
            "Offline-first clinical encounter form scanner, open-weight handwriting "
            "extractor, medical auto-coder, and native IBM SPSS (.sav) backend."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(projects_router, prefix="/api/v1")
    app.include_router(merge_router, prefix="/api/v1")
    app.include_router(transforms_router, prefix="/api/v1")
    app.include_router(exports_router, prefix="/api/v1")

    return app


app = create_app()
