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
    """Convenience wrapper: build a ``CostDelta`` from keyword args and record it.

    This is a thin façade over ``record_cost_delta``; it exists so that
    callers don't need to import ``CostDelta`` / ``CostCategory`` /
    ``Currency`` for simple one-off recordings.
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
