"""yuutrace -- LLM-oriented observability SDK built on OpenTelemetry.

Public API
----------

Types::

    CostCategory, Currency
    CostDelta, LlmUsageDelta, ToolUsageDelta

Context managers::

    conversation(*, id, agent, model, tags=None) -> ConversationContext
    ConversationContext.llm_gen() -> LlmGenContext
    ConversationContext.tools() -> ToolsContext

Recording (recommended wrappers)::

    record_cost(*, category, currency, amount, ...)
    record_cost_delta(cost: CostDelta)
    record_llm_usage(usage_or_kwargs)
    record_tool_usage(usage: ToolUsageDelta)

Low-level::

    current_span() -> Span
    add_event(name, attributes)
"""

from __future__ import annotations

# -- Types -----------------------------------------------------------------
from .types import (
    CostCategory,
    CostDelta,
    Currency,
    LlmUsageDelta,
    ToolUsageDelta,
)

# -- Context managers ------------------------------------------------------
from .context import (
    ConversationContext,
    LlmGenContext,
    ToolResult,
    ToolsContext,
    conversation,
)

# -- Recording wrappers ----------------------------------------------------
from .cost import record_cost, record_cost_delta
from .usage import record_llm_usage, record_tool_usage

# -- Low-level -------------------------------------------------------------
from .span import NoActiveSpanError, add_event, current_span

__all__ = [
    # Types
    "CostCategory",
    "Currency",
    "CostDelta",
    "LlmUsageDelta",
    "ToolUsageDelta",
    # Context managers
    "conversation",
    "ConversationContext",
    "LlmGenContext",
    "ToolsContext",
    "ToolResult",
    # Recording
    "record_cost",
    "record_cost_delta",
    "record_llm_usage",
    "record_tool_usage",
    # Low-level
    "current_span",
    "add_event",
    "NoActiveSpanError",
]
