"""WebUI server for trace visualization.

Implements ``ytrace ui`` -- serves the @yuutrace/ui pre-built static
assets alongside a REST API that queries trace data from SQLite.

Usage::

    ytrace ui --db ./traces.db --port 8080
"""

from __future__ import annotations

import importlib.resources
import logging
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .db import get_conversation, get_span, init_db, list_conversations

logger = logging.getLogger("yuutrace.ui")


# ---------------------------------------------------------------------------
# API handlers
# ---------------------------------------------------------------------------


async def _health(request: Request) -> JSONResponse:
    """GET /api/health"""
    return JSONResponse({"status": "ok"})


async def _list_conversations(request: Request) -> JSONResponse:
    """GET /api/conversations?limit=50&offset=0&agent=..."""
    limit = int(request.query_params.get("limit", "50"))
    offset = int(request.query_params.get("offset", "0"))
    agent = request.query_params.get("agent")

    result = list_conversations(
        request.app.state.db,
        limit=limit,
        offset=offset,
        agent=agent or None,
    )
    return JSONResponse(result)


async def _get_conversation(request: Request) -> JSONResponse:
    """GET /api/conversations/{id}"""
    conversation_id = request.path_params["id"]
    result = get_conversation(request.app.state.db, conversation_id)
    if result is None:
        return JSONResponse({"error": "Conversation not found"}, status_code=404)
    return JSONResponse(result)


async def _get_span(request: Request) -> JSONResponse:
    """GET /api/spans/{id}"""
    span_id = request.path_params["id"]
    result = get_span(request.app.state.db, span_id)
    if result is None:
        return JSONResponse({"error": "Span not found"}, status_code=404)
    return JSONResponse(result)


# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------


def _resolve_static_dir() -> Path:
    """Locate the pre-built static assets directory.

    Uses ``importlib.resources`` so it works both in editable installs
    and from wheel/sdist.
    """
    try:
        ref = importlib.resources.files("yuutrace.cli._static")
        # as_posix() works for both Path and Traversable
        static_path = Path(str(ref))
        if static_path.is_dir():
            return static_path
    except (ModuleNotFoundError, TypeError):
        pass

    # Fallback: relative to this file
    fallback = Path(__file__).parent / "_static"
    return fallback


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def _build_app(db_path: str) -> Starlette:
    """Create the Starlette ASGI application."""
    static_dir = _resolve_static_dir()
    logger.info("Static assets directory: %s", static_dir)

    # API routes come first (Starlette matches in order)
    routes: list[Route | Mount] = [
        Route("/api/health", _health, methods=["GET"]),
        Route("/api/conversations", _list_conversations, methods=["GET"]),
        Route("/api/conversations/{id:path}", _get_conversation, methods=["GET"]),
        Route("/api/spans/{id:path}", _get_span, methods=["GET"]),
    ]

    # Mount static files last — html=True enables SPA fallback
    if static_dir.is_dir() and any(static_dir.iterdir()):
        routes.append(
            Mount("/", app=StaticFiles(directory=str(static_dir), html=True)),
        )
    else:
        logger.warning(
            "Static assets not found at %s. "
            "Run 'scripts/build_ui.sh' to build the frontend.",
            static_dir,
        )

    app = Starlette(routes=routes)
    app.state.db = init_db(db_path)
    return app


def run_ui(*, db_path: str, port: int) -> None:
    """Start the WebUI server.

    The server does two things:
    1. Provides REST API endpoints that query trace data from SQLite.
    2. Serves the pre-built static assets from @yuutrace/ui (TracePage).

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.
    port:
        Port for the HTTP server.
    """
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logger.info("Starting yuutrace UI on port %d (db: %s)", port, db_path)

    app = _build_app(db_path)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
