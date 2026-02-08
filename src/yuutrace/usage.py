"""Usage recording wrappers.

Business code should use ``record_llm_usage()`` or ``record_tool_usage()``
to record incremental usage events.  These functions handle OTEL
event naming and attribute serialization internally.
"""

from __future__ import annotations

from typing import overload

from .otel import (
    EVENT_LLM_USAGE,
    EVENT_TOOL_USAGE,
    llm_usage_to_otel,
    tool_usage_to_otel,
)
from .span import add_event
from .types import LlmUsageDelta, ToolUsageDelta


# ---------------------------------------------------------------------------
# LLM usage
# ---------------------------------------------------------------------------


@overload
def record_llm_usage(usage: LlmUsageDelta) -> None: ...


@overload
def record_llm_usage(
    *,
    provider: str,
    model: str,
    request_id: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    total_tokens: int | None = None,
) -> None: ...


def record_llm_usage(
    usage: LlmUsageDelta | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
    request_id: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    total_tokens: int | None = None,
) -> None:
    """Record an incremental LLM token usage event on the current span.

    Accepts either a pre-built ``LlmUsageDelta`` **or** keyword arguments
    that will be used to construct one.

    Raises
    ------
    NoActiveSpanError
        If there is no active recording span.
    TypeError
        If neither a struct instance nor the required keyword arguments
        (``provider``, ``model``) are supplied.
    """
    if usage is None:
        if provider is None or model is None:
            raise TypeError(
                "record_llm_usage() requires either a LlmUsageDelta instance "
                "or 'provider' and 'model' keyword arguments."
            )
        usage = LlmUsageDelta(
            provider=provider,
            model=model,
            request_id=request_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            total_tokens=total_tokens,
        )
    add_event(EVENT_LLM_USAGE, llm_usage_to_otel(usage))


# ---------------------------------------------------------------------------
# Tool usage
# ---------------------------------------------------------------------------


def record_tool_usage(usage: ToolUsageDelta) -> None:
    """Record an incremental tool usage event on the current span.

    Only record when the tool has a meaningful, well-defined usage metric
    (e.g. bytes transferred, seconds elapsed, API request count).

    Parameters
    ----------
    usage:
        A fully constructed ``ToolUsageDelta`` instance.

    Raises
    ------
    NoActiveSpanError
        If there is no active recording span.
    """
    add_event(EVENT_TOOL_USAGE, tool_usage_to_otel(usage))
