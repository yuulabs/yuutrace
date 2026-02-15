"""Cost recording wrappers.

Business code should use ``record_cost()`` or ``record_cost_delta()``
to record incremental cost events.  These functions handle OTEL
event naming and attribute serialization internally.
"""

from __future__ import annotations

from .otel import EVENT_COST, cost_delta_to_otel
from .span import add_event
from .types import CostCategory, CostDelta, Currency


def record_cost_delta(cost: CostDelta) -> None:
    """Record an incremental cost event on the current span.

    Parameters
    ----------
    cost:
        A fully constructed ``CostDelta`` instance.

    Raises
    ------
    NoActiveSpanError
        If there is no active recording span.
    """
    add_event(EVENT_COST, cost_delta_to_otel(cost))


def record_cost(
    *,
    category: CostCategory | str,
    currency: Currency | str,
    amount: float,
    source: str | None = None,
    pricing_id: str | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    llm_request_id: str | None = None,
    tool_name: str | None = None,
    tool_call_id: str | None = None,
) -> None:
    """Build a ``CostDelta`` from keyword args and record it on the current span.

    This is a convenience wrapper over ``record_cost_delta`` so that callers
    don't need to import ``CostDelta`` / ``CostCategory`` / ``Currency``.

    Parameters
    ----------
    category:
        ``"llm"`` or ``"tool"`` (accepts ``CostCategory`` enum or plain str).
    currency:
        Currency code, currently only ``"USD"`` (accepts ``Currency`` or str).
    amount:
        Incremental cost in the given currency.
    source:
        Free-form source label (e.g. ``"openai-api"``).
    pricing_id:
        Identifier for the pricing rule that produced this cost.
    llm_provider:
        LLM provider name (when ``category="llm"``).
    llm_model:
        LLM model name (when ``category="llm"``).
    llm_request_id:
        LLM request ID for correlation.
    tool_name:
        Tool name (when ``category="tool"``).
    tool_call_id:
        Tool call ID for correlation.

    Raises
    ------
    NoActiveSpanError
        If there is no active recording span.
    """
    record_cost_delta(
        CostDelta(
            category=CostCategory(category),
            currency=Currency(currency),
            amount=amount,
            source=source,
            pricing_id=pricing_id,
            llm_provider=llm_provider,
            llm_model=llm_model,
            llm_request_id=llm_request_id,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
        )
    )
