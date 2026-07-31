from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger("mediscribe.errors")

GENERIC_MESSAGE = "Something went wrong on our end. Please try again in a moment."
DB_UNAVAILABLE_MESSAGE = "The service is temporarily busy. Please try again in a few seconds."


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


async def request_id_middleware(request: Request, call_next) -> JSONResponse:
    request.state.request_id = request.headers.get("x-request-id") or str(uuid4())
    response = await call_next(request)
    response.headers["x-request-id"] = request.state.request_id
    return response


def _error_body(status_code: int, detail: str, error_code: str, request: Request) -> dict:
    body: dict = {
        "status_code": status_code,
        "detail": detail,
        "error_code": error_code,
    }
    rid = _request_id(request)
    if rid:
        body["request_id"] = rid
    return body


async def db_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.error(
        "DB error on %s %s (request_id=%s): %s",
        request.method,
        request.url.path,
        _request_id(request),
        exc,
    )
    return JSONResponse(
        status_code=503,
        content=_error_body(503, DB_UNAVAILABLE_MESSAGE, "service_unavailable", request),
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.warning(
        "Validation error on %s %s (request_id=%s): %s",
        request.method,
        request.url.path,
        _request_id(request),
        exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content={
            **_error_body(422, "Request is missing required fields or has invalid values.", "validation_error", request),
            "errors": exc.errors(),
        },
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled error on %s %s (request_id=%s)",
        request.method,
        request.url.path,
        _request_id(request),
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        content=_error_body(500, GENERIC_MESSAGE, "internal_error", request),
    )
