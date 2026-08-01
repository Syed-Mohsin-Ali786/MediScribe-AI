from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from app.api import api_router
from app.core.config import get_settings
from app.core.errors import (
    db_error_handler,
    request_id_middleware,
    unhandled_error_handler,
    validation_error_handler,
)
from app.services.supabase_storage import MEDIA_DIR

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="AI-powered medical SOAP notes from doctor-patient conversations.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(request_id_middleware)

app.add_exception_handler(SQLAlchemyError, db_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)

app.include_router(api_router, prefix="/api/v1")

# Serve consultation audio files persisted under media/.
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")


@app.get("/health", tags=["health"])
async def health() -> dict:
    database = "connected"
    try:
        from sqlalchemy import text

        from app.core.database import engine

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        database = "unreachable"
    return {"status": "ok", "app": settings.app_name, "database": database}
