from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api import api_router
from app.core.asyncio import ensure_psycopg_compatible_loop, loop_supports_psycopg
from app.core.config import UPLOADS_DIR, get_settings
from app.core.errors import (
    data_conflict_handler,
    db_error_handler,
    request_id_middleware,
    unhandled_error_handler,
    validation_error_handler,
)
from app.services.supabase_storage import MEDIA_DIR

logger = logging.getLogger("mediscribe.app")

settings = get_settings()

# Safety net: makes the default policy psycopg-friendly on Windows. Uvicorn
# passes an explicit loop factory, so the real fix is starting the server with
# `--loop app.core.asyncio:selector_loop_factory` (see app/server.py).
ensure_psycopg_compatible_loop()

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Fail loudly if the running event loop cannot talk to psycopg.

    Without this, a Windows server started without ``--reload`` silently runs
    on a ProactorEventLoop and every database request comes back as a
    misleading 503 "the service is temporarily busy".
    """
    loop = asyncio.get_running_loop()
    if not loop_supports_psycopg(loop):
        logger.error(
            "Event loop %s is not compatible with psycopg's async driver — every database "
            "request will fail. Start the server with "
            "'--loop app.core.asyncio:selector_loop_factory' (or use 'python -m app.server').",
            type(loop).__name__,
        )
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="AI-powered medical SOAP notes from doctor-patient conversations.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(request_id_middleware)

# Registered most-specific first: Starlette resolves handlers by walking the
# exception's MRO, so IntegrityError is matched before SQLAlchemyError.
app.add_exception_handler(IntegrityError, data_conflict_handler)
app.add_exception_handler(SQLAlchemyError, db_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)

app.include_router(api_router, prefix="/api/v1")

# Serve consultation audio files persisted under media/.
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")

# Serve uploaded profile photos persisted under uploads/.
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")


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
