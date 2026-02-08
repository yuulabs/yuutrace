"""SQLite persistence layer for yuutrace.

Stores OTLP trace data in a local SQLite database and provides
query functions for the REST API.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS spans (
    trace_id             TEXT NOT NULL,
    span_id              TEXT NOT NULL PRIMARY KEY,
    parent_span_id       TEXT,
    name                 TEXT NOT NULL,
    start_time_unix_nano INTEGER NOT NULL,
    end_time_unix_nano   INTEGER NOT NULL,
    status_code          INTEGER NOT NULL DEFAULT 0,
    status_message       TEXT,
    attributes_json      TEXT NOT NULL DEFAULT '{}',
    conversation_id      TEXT,
    agent                TEXT,
    model                TEXT,
    resource_json        TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_spans_conversation_id
    ON spans(conversation_id);
CREATE INDEX IF NOT EXISTS idx_spans_trace_id
    ON spans(trace_id);
CREATE INDEX IF NOT EXISTS idx_spans_start_time
    ON spans(start_time_unix_nano);

CREATE TABLE IF NOT EXISTS events (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    span_id           TEXT NOT NULL REFERENCES spans(span_id),
    name              TEXT NOT NULL,
    time_unix_nano    INTEGER NOT NULL,
    attributes_json   TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_events_span_id
    ON events(span_id);
CREATE INDEX IF NOT EXISTS idx_events_name
    ON events(name);
"""


def init_db(db_path: str) -> sqlite3.Connection:
    """Open (or create) the database and ensure the schema exists."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# OTLP JSON helpers
# ---------------------------------------------------------------------------


def _otlp_attr_value(attr: dict[str, Any]) -> Any:
    """Extract the typed value from an OTLP attribute entry.

    OTLP JSON encodes attribute values as ``{"stringValue": "..."}`` etc.
    """
    if "stringValue" in attr:
        return attr["stringValue"]
    if "intValue" in attr:
        return int(attr["intValue"])
    if "doubleValue" in attr:
        return float(attr["doubleValue"])
    if "boolValue" in attr:
        return attr["boolValue"]
    if "arrayValue" in attr:
        values = attr["arrayValue"].get("values", [])
        return [_otlp_attr_value(v) for v in values]
    if "bytesValue" in attr:
        return attr["bytesValue"]
    if "kvlistValue" in attr:
        pairs = attr["kvlistValue"].get("values", [])
        return {p["key"]: _otlp_attr_value(p.get("value", {})) for p in pairs}
    # Fallback: return the raw dict
    return attr


def _parse_attributes(attr_list: list[dict[str, Any]]) -> dict[str, Any]:
    """Convert an OTLP ``attributes`` array to a flat dict."""
    return {a["key"]: _otlp_attr_value(a.get("value", {})) for a in attr_list}


def _parse_resource_attributes(resource: dict[str, Any]) -> dict[str, Any]:
    """Extract resource-level attributes."""
    return _parse_attributes(resource.get("attributes", []))


# ---------------------------------------------------------------------------
# Insert
# ---------------------------------------------------------------------------


def insert_resource_spans(conn: sqlite3.Connection, resource_spans: list[dict[str, Any]]) -> int:
    """Parse OTLP JSON ``resourceSpans`` and insert into the database.

    Returns the number of spans inserted.
    """
    count = 0
    for rs in resource_spans:
        resource_attrs = _parse_resource_attributes(rs.get("resource", {}))
        resource_json = json.dumps(resource_attrs)

        for ss in rs.get("scopeSpans", []):
            for span in ss.get("spans", []):
                attrs = _parse_attributes(span.get("attributes", []))
                attrs_json = json.dumps(attrs)

                # Denormalized fields from attributes
                conversation_id = attrs.get("yuu.conversation.id")
                agent = attrs.get("yuu.agent")
                model = attrs.get("yuu.conversation.model")

                # Status
                status = span.get("status", {})
                status_code = status.get("code", 0)
                status_message = status.get("message")

                span_id = span["spanId"]

                conn.execute(
                    """INSERT OR REPLACE INTO spans
                       (trace_id, span_id, parent_span_id, name,
                        start_time_unix_nano, end_time_unix_nano,
                        status_code, status_message, attributes_json,
                        conversation_id, agent, model, resource_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        span["traceId"],
                        span_id,
                        span.get("parentSpanId"),
                        span.get("name", ""),
                        int(span.get("startTimeUnixNano", 0)),
                        int(span.get("endTimeUnixNano", 0)),
                        status_code,
                        status_message,
                        attrs_json,
                        conversation_id,
                        agent,
                        model,
                        resource_json,
                    ),
                )

                # Events
                for event in span.get("events", []):
                    event_attrs = _parse_attributes(event.get("attributes", []))
                    conn.execute(
                        """INSERT INTO events
                           (span_id, name, time_unix_nano, attributes_json)
                           VALUES (?, ?, ?, ?)""",
                        (
                            span_id,
                            event.get("name", ""),
                            int(event.get("timeUnixNano", 0)),
                            json.dumps(event_attrs),
                        ),
                    )

                count += 1

    conn.commit()
    return count


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def _enrich_span(span_dict: dict[str, Any]) -> dict[str, Any]:
    """Parse JSON blobs back into dicts for API responses."""
    span_dict["attributes"] = json.loads(span_dict.get("attributes_json") or "{}")
    span_dict["resource"] = json.loads(span_dict.get("resource_json") or "{}")
    del span_dict["attributes_json"]
    del span_dict["resource_json"]
    return span_dict


def _attach_events(conn: sqlite3.Connection, spans: list[dict[str, Any]]) -> None:
    """Attach events to each span dict in-place."""
    if not spans:
        return
    span_ids = [s["span_id"] for s in spans]
    placeholders = ",".join("?" * len(span_ids))
    rows = conn.execute(
        f"SELECT * FROM events WHERE span_id IN ({placeholders}) ORDER BY time_unix_nano",
        span_ids,
    ).fetchall()

    events_by_span: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        ev = _row_to_dict(row)
        ev["attributes"] = json.loads(ev.get("attributes_json") or "{}")
        del ev["attributes_json"]
        events_by_span.setdefault(ev["span_id"], []).append(ev)

    for span in spans:
        span["events"] = events_by_span.get(span["span_id"], [])


def list_conversations(
    conn: sqlite3.Connection,
    *,
    limit: int = 50,
    offset: int = 0,
    agent: str | None = None,
) -> dict[str, Any]:
    """Return a paginated list of conversations with summary stats.

    Returns ``{"conversations": [...], "total": int}``.
    """
    where = "WHERE conversation_id IS NOT NULL"
    params: list[Any] = []
    if agent:
        where += " AND agent = ?"
        params.append(agent)

    # Total count
    total = conn.execute(
        f"SELECT COUNT(DISTINCT conversation_id) FROM spans {where}",
        params,
    ).fetchone()[0]

    # Summaries — join with all spans sharing the same trace_id
    # so child spans (llm_gen, tool:*) are counted too.
    rows = conn.execute(
        f"""SELECT
                root.conversation_id AS id,
                root.agent,
                root.model,
                root.trace_id,
                COUNT(all_spans.span_id) AS span_count,
                MIN(all_spans.start_time_unix_nano) AS start_time,
                MAX(all_spans.end_time_unix_nano) AS end_time
            FROM spans root
            JOIN spans all_spans ON all_spans.trace_id = root.trace_id
            {where.replace("conversation_id", "root.conversation_id").replace("agent", "root.agent")}
            GROUP BY root.conversation_id
            ORDER BY start_time DESC
            LIMIT ? OFFSET ?""",
        [*params, limit, offset],
    ).fetchall()

    conversations = []
    for row in rows:
        d = _row_to_dict(row)
        trace_id = d.pop("trace_id")
        # Compute total cost from all events in this trace
        cost_row = conn.execute(
            """SELECT COALESCE(SUM(
                   json_extract(e.attributes_json, '$."yuu.cost.amount"')
               ), 0) AS total_cost
               FROM events e
               JOIN spans s ON e.span_id = s.span_id
               WHERE s.trace_id = ? AND e.name = 'yuu.cost'""",
            (trace_id,),
        ).fetchone()
        d["total_cost"] = cost_row[0] if cost_row else 0.0
        conversations.append(d)

    return {"conversations": conversations, "total": total}


def get_conversation(conn: sqlite3.Connection, conversation_id: str) -> dict[str, Any] | None:
    """Return all spans and events for a single conversation.

    Finds the root span by conversation_id, then fetches ALL spans
    sharing the same trace_id (including children like llm_gen, tool:*).
    """
    # Find the root span to get the trace_id
    root_row = conn.execute(
        "SELECT trace_id FROM spans WHERE conversation_id = ? LIMIT 1",
        (conversation_id,),
    ).fetchone()
    if root_row is None:
        return None

    trace_id = root_row["trace_id"]

    # Fetch all spans in this trace
    rows = conn.execute(
        """SELECT * FROM spans
           WHERE trace_id = ?
           ORDER BY start_time_unix_nano""",
        (trace_id,),
    ).fetchall()

    if not rows:
        return None

    spans = [_enrich_span(_row_to_dict(r)) for r in rows]
    _attach_events(conn, spans)

    # Aggregate metadata from the root conversation span
    root = spans[0]
    agent = root.get("agent", "")
    model = root.get("model")
    tags = root["attributes"].get("yuu.conversation.tags")

    # Total cost
    span_ids = [s["span_id"] for s in spans]
    placeholders = ",".join("?" * len(span_ids))
    cost_row = conn.execute(
        f"""SELECT COALESCE(SUM(
               json_extract(attributes_json, '$."yuu.cost.amount"')
           ), 0)
           FROM events
           WHERE span_id IN ({placeholders}) AND name = 'yuu.cost'""",
        span_ids,
    ).fetchone()

    return {
        "id": conversation_id,
        "agent": agent,
        "model": model,
        "tags": tags,
        "spans": spans,
        "total_cost": cost_row[0] if cost_row else 0.0,
        "start_time": spans[0]["start_time_unix_nano"],
        "end_time": max(s["end_time_unix_nano"] for s in spans),
    }


def get_span(conn: sqlite3.Connection, span_id: str) -> dict[str, Any] | None:
    """Return a single span with its events."""
    row = conn.execute("SELECT * FROM spans WHERE span_id = ?", (span_id,)).fetchone()
    if row is None:
        return None

    span = _enrich_span(_row_to_dict(row))
    _attach_events(conn, [span])
    return span
