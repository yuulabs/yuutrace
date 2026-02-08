"""Low-level span access and event recording.

Provides ``current_span()`` and ``add_event()`` -- the building blocks
on which the higher-level wrappers in ``cost.py`` and ``usage.py`` are built.
"""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.trace import Span, StatusCode

from .otel import OtelAttributes


class NoActiveSpanError(RuntimeError):
    """Raised when ``current_span()`` finds no active span.

    yuutrace follows a **fast-fail** policy: callers must ensure a span is
    active before writing observability data.  Silent fallback to a no-op
    span would hide instrumentation mistakes.
    """


def current_span() -> Span:
    """Return the currently active OTEL span.

    Raises
    ------
    NoActiveSpanError
        If there is no active span (i.e. the returned span is a
        ``NonRecordingSpan`` / ``INVALID_SPAN``).
    """
    span = trace.get_current_span()
    if not span.is_recording():
        raise NoActiveSpanError(
            "No active recording span. "
            "Wrap your code in a yuutrace context manager "
            "(e.g. ytrace.conversation()) before recording events."
        )
    return span


def add_event(name: str, attributes: OtelAttributes) -> None:
    """Add an event to the current span.

    This is the **internal** primitive used by ``record_cost_delta``,
    ``record_llm_usage``, etc.  Business code should use the typed
    wrapper functions instead of calling this directly.

    Raises
    ------
    NoActiveSpanError
        Propagated from ``current_span()`` if no span is active.
    """
    span = current_span()
    span.add_event(name, attributes=attributes)  # type: ignore[arg-type]


def set_span_error(error: BaseException) -> None:
    """Mark the current span as errored with the given exception."""
    span = current_span()
    span.set_status(StatusCode.ERROR, str(error))
    span.record_exception(error)
