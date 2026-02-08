"""OTEL Collector + SQLite storage backend.

Implements ``ytrace server`` -- receives OTLP/HTTP JSON trace data
and persists it to a SQLite database via :mod:`yuutrace.cli.db`.

Usage::

    ytrace server --db ./traces.db --port 4318

SDK-side configuration::

    OTEL_EXPORTER_OTLP_PROTOCOL=http/json
    OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
"""

from __future__ import annotations

import json
import logging

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .db import init_db, insert_resource_spans

logger = logging.getLogger("yuutrace.server")


async def _receive_traces(request: Request) -> Response:
    """POST /v1/traces — receive OTLP/HTTP JSON and persist to SQLite."""
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type and "application/x-protobuf" not in content_type:
        # Be lenient: also accept missing content-type
        if content_type:
            return JSONResponse(
                {"error": "Unsupported content type. Use application/json."},
                status_code=415,
            )

    if "application/x-protobuf" in content_type:
        return JSONResponse(
            {"error": "Protobuf encoding is not supported. Use http/json."},
            status_code=415,
        )

    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError) as exc:
        return JSONResponse({"error": f"Invalid JSON: {exc}"}, status_code=400)

    resource_spans = body.get("resourceSpans", [])
    if not resource_spans:
        return JSONResponse({"partialSuccess": None})

    try:
        count = insert_resource_spans(request.app.state.db, resource_spans)
        logger.info("Inserted %d spans", count)
    except Exception:
        logger.exception("Failed to insert spans")
        return JSONResponse({"error": "Internal storage error"}, status_code=500)

    return JSONResponse({"partialSuccess": None})


def _build_app(db_path: str) -> Starlette:
    """Create the Starlette ASGI application."""
    routes = [
        Route("/v1/traces", _receive_traces, methods=["POST"]),
    ]
    app = Starlette(routes=routes)
    app.state.db = init_db(db_path)
    return app


def run_server(*, db_path: str, port: int) -> None:
    """Start the OTEL collector + SQLite storage server.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.
    port:
        Port for the OTEL HTTP receiver.
    """
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logger.info("Starting yuutrace collector on port %d (db: %s)", port, db_path)

    app = _build_app(db_path)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
