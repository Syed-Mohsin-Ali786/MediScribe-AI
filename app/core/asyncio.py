from __future__ import annotations

import asyncio
import sys


def selector_loop_factory(use_subprocess: bool = False) -> asyncio.AbstractEventLoop:
    """Event loop factory that psycopg's async driver can actually use.

    psycopg's async implementation needs ``loop.add_reader``, which
    ``ProactorEventLoop`` (the Windows default) does not provide. Uvicorn picks
    ``ProactorEventLoop`` on Windows *unless* it is running with ``--reload``
    or ``--workers`` (see ``uvicorn.loops.asyncio.asyncio_loop_factory``), so a
    plain ``uvicorn app.main:app`` on Windows fails every database query with
    "Psycopg cannot use the 'ProactorEventLoop' to run in async mode".

    Passing this factory via ``--loop app.core.asyncio:selector_loop_factory``
    makes the API behave the same however it is started.
    """
    return asyncio.SelectorEventLoop()


def ensure_psycopg_compatible_loop() -> None:
    """Best-effort: make the default policy psycopg-friendly on Windows.

    Covers the cases where the event loop is created from the policy rather
    than from an explicit factory. Uvicorn passes an explicit factory, so this
    is a safety net rather than the primary fix.
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def loop_supports_psycopg(loop: asyncio.AbstractEventLoop) -> bool:
    """True when the loop implements the selector APIs psycopg needs."""
    return hasattr(loop, "add_reader") and hasattr(loop, "add_writer")
