"""In-memory trace store for testing.

Uses :memory: SQLite with the same schema as ``cli/db.py``, so the full
query API (list_conversations, get_conversation, get_span) is available
without any external collector.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from .cli.db import (
    _SCHEMA,
    get_conversation,
    get_span,
    insert_resource_spans,
    list_conversations,
)


def _span_to_otlp_json(span: ReadableSpan) -> dict[str, Any]:
    """Convert an SDK ReadableSpan to OTLP-style JSON dict."""
    ctx = span.get_span_context()

    # Attributes
    attrs = []
    for k, v in (span.attributes or {}).items():
        if isinstance(v, str):
            attrs.append({"key": k, "value": {"stringValue": v}})
        elif isinstance(v, bool):
            attrs.append({"key": k, "value": {"boolValue": v}})
        elif isinstance(v, int):
            attrs.append({"key": k, "value": {"intValue": str(v)}})
        elif isinstance(v, float):
            attrs.append({"key": k, "value": {"doubleValue": v}})
        elif isinstance(v, (list, tuple)):
            values = []
            for item in v:
                if isinstance(item, str):
                    values.append({"stringValue": item})
                elif isinstance(item, int):
                    values.append({"intValue": str(item)})
                elif isinstance(item, float):
                    values.append({"doubleValue": item})
            attrs.append({"key": k, "value": {"arrayValue": {"values": values}}})

    # Events
    events = []
    for ev in span.events or []:
        ev_attrs = []
        for ek, ev_val in (ev.attributes or {}).items():
            if isinstance(ev_val, str):
                ev_attrs.append({"key": ek, "value": {"stringValue": ev_val}})
            elif isinstance(ev_val, int):
                ev_attrs.append({"key": ek, "value": {"intValue": str(ev_val)}})
            elif isinstance(ev_val, float):
                ev_attrs.append({"key": ek, "value": {"doubleValue": ev_val}})
        events.append({
            "name": ev.name,
            "timeUnixNano": str(ev.timestamp or 0),
            "attributes": ev_attrs,
        })

    # Status
    status: dict[str, Any] = {}
    if span.status is not None:
        status["code"] = span.status.status_code.value
        if span.status.description:
            status["message"] = span.status.description

    parent_id = None
    if span.parent is not None:
        parent_id = format(span.parent.span_id, "016x")

    return {
        "traceId": format(ctx.trace_id, "032x"),
        "spanId": format(ctx.span_id, "016x"),
        "parentSpanId": parent_id,
        "name": span.name,
        "startTimeUnixNano": str(span.start_time or 0),
        "endTimeUnixNano": str(span.end_time or 0),
        "status": status,
        "attributes": attrs,
        "events": events,
    }


class _MemoryExporter(SpanExporter):
    """SpanExporter that writes finished spans into an in-memory SQLite DB."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def export(self, spans: Any) -> SpanExportResult:
        resource_spans_list: list[dict[str, Any]] = []

        for span in spans:
            # Build resource attributes from span resource
            res_attrs = []
            if hasattr(span, "resource") and span.resource:
                for k, v in span.resource.attributes.items():
                    if isinstance(v, str):
                        res_attrs.append({"key": k, "value": {"stringValue": v}})
                    elif isinstance(v, int):
                        res_attrs.append({"key": k, "value": {"intValue": str(v)}})

            resource_spans_list.append({
                "resource": {"attributes": res_attrs},
                "scopeSpans": [{
                    "spans": [_span_to_otlp_json(span)],
                }],
            })

        insert_resource_spans(self._conn, resource_spans_list)
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass


class MemoryTraceStore:
    """In-memory trace store for testing.

    Wraps a :memory: SQLite database with the yuutrace schema.
    Provides the same query API as ``cli/db.py``.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def list_conversations(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        agent: str | None = None,
    ) -> dict[str, Any]:
        return list_conversations(self.conn, limit=limit, offset=offset, agent=agent)

    def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        return get_conversation(self.conn, conversation_id)

    def get_span(self, span_id: str) -> dict[str, Any] | None:
        return get_span(self.conn, span_id)

    def get_all_spans(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM spans ORDER BY start_time_unix_nano"
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["attributes"] = json.loads(d.get("attributes_json") or "{}")
            d["resource"] = json.loads(d.get("resource_json") or "{}")
            del d["attributes_json"]
            del d["resource_json"]
            result.append(d)
        return result
