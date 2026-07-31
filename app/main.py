from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError

from app.api import api_router
from app.core.config import get_settings
from app.core.errors import (
    db_error_handler,
    request_id_middleware,
    unhandled_error_handler,
    validation_error_handler,
)

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


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok", "app": settings.app_name}
