"""High-level context managers for structured tracing.

Provides ``conversation()``, ``ConversationContext.llm_gen()``, and
``ConversationContext.tools()`` -- the recommended entry points for
instrumenting LLM agent workloads.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import msgspec
from opentelemetry import context as otel_context
from opentelemetry import trace

from .otel import (
    ATTR_AGENT,
    ATTR_CONTEXT_SYSTEM_PERSONA,
    ATTR_CONTEXT_SYSTEM_TOOLS,
    ATTR_CONTEXT_USER_CONTENT,
    ATTR_CONVERSATION_ID,
    ATTR_CONVERSATION_MODEL,
    ATTR_CONVERSATION_TAGS,
    ATTR_LLM_GEN_ITEMS,
)
from .span import set_span_error

_tracer = trace.get_tracer("yuutrace")


# ---------------------------------------------------------------------------
# ToolResult
# ---------------------------------------------------------------------------


class ToolResult(msgspec.Struct, frozen=True):
    """Result of a single tool invocation inside a ``tools()`` block."""

    tool_call_id: str
    output: Any
    error: str | None = None


# ---------------------------------------------------------------------------
# LlmGenContext
# ---------------------------------------------------------------------------


class LlmGenContext:
    """Context returned by ``ConversationContext.llm_gen()``.

    Allows logging the raw LLM response items on the current llm span.
    """

    __slots__ = ("_span",)

    def __init__(self, span: trace.Span) -> None:
        self._span = span

    def log(self, items: list[Any]) -> None:
        """Attach LLM response items as a span attribute.

        *items* is serialized to JSON so it fits into an OTEL string
        attribute.
        """
        serialized = json.dumps(items, default=str)
        self._span.set_attribute(ATTR_LLM_GEN_ITEMS, serialized)


# ---------------------------------------------------------------------------
# ToolsContext
# ---------------------------------------------------------------------------


class ToolsContext:
    """Context returned by ``ConversationContext.tools()``.

    Provides ``gather()`` for concurrent tool execution with per-call
    child spans.
    """

    __slots__ = ("_parent_span", "_tracer")

    def __init__(self, parent_span: trace.Span, tracer: trace.Tracer) -> None:
        self._parent_span = parent_span
        self._tracer = tracer

    async def gather(
        self,
        calls: list[dict[str, Any]],
    ) -> list[ToolResult]:
        """Execute tool calls and return their results.

        Each *call* dict must contain:
        - ``tool_call_id``: str
        - ``tool``: an async callable (or sync callable)
        - ``params``: dict of keyword arguments

        A child span is created for each tool invocation.
        """
        import asyncio

        async def _run_one(call: dict[str, Any]) -> ToolResult:
            tool_call_id: str = call["tool_call_id"]
            tool_fn: Callable[..., Any] = call["tool"]
            params: dict[str, Any] = call.get("params", {})
            tool_name = getattr(tool_fn, "__name__", str(tool_fn))

            # Create a child span linked to the tools span context
            with self._tracer.start_as_current_span(
                f"tool:{tool_name}",
                attributes={
                    "yuu.tool.name": tool_name,
                    "yuu.tool.call_id": tool_call_id,
                },
            ) as tool_span:
                try:
                    result = tool_fn(**params)
                    if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                        result = await result
                    return ToolResult(tool_call_id=tool_call_id, output=result)
                except Exception as exc:
                    set_span_error(exc)
                    return ToolResult(
                        tool_call_id=tool_call_id,
                        output=None,
                        error=f"{type(exc).__name__}: {exc}",
                    )

        results = await asyncio.gather(*[_run_one(c) for c in calls])
        return list(results)


# ---------------------------------------------------------------------------
# ConversationContext
# ---------------------------------------------------------------------------


class ConversationContext:
    """Context returned by ``conversation()``.

    Provides methods to record system prompts, user messages, and to
    open child spans for LLM generation and tool execution.
    """

    __slots__ = ("_span", "_tracer")

    def __init__(self, span: trace.Span, tracer: trace.Tracer) -> None:
        self._span = span
        self._tracer = tracer

    # -- message logging ---------------------------------------------------

    def system(self, persona: str, tools: list[Any] | None = None) -> None:
        """Record the system prompt and (optionally) tool specifications."""
        self._span.set_attribute(ATTR_CONTEXT_SYSTEM_PERSONA, persona)
        if tools is not None:
            serialized = json.dumps(tools, default=str)
            self._span.set_attribute(ATTR_CONTEXT_SYSTEM_TOOLS, serialized)

    def user(self, content: str) -> None:
        """Record a user message."""
        self._span.set_attribute(ATTR_CONTEXT_USER_CONTENT, content)

    # -- child contexts ----------------------------------------------------

    @contextmanager
    def llm_gen(self) -> Iterator[LlmGenContext]:
        """Open a child span for an LLM generation step.

        Usage::

            with chat.llm_gen() as gen:
                ...
                gen.log(items)
        """
        with self._tracer.start_as_current_span("llm_gen") as span:
            ctx = LlmGenContext(span)
            try:
                yield ctx
            except Exception as exc:
                set_span_error(exc)
                raise

    @contextmanager
    def tools(self) -> Iterator[ToolsContext]:
        """Open a child span for a batch of tool calls.

        Usage::

            with chat.tools() as t:
                results = await t.gather([...])
        """
        with self._tracer.start_as_current_span("tools") as span:
            ctx = ToolsContext(span, self._tracer)
            try:
                yield ctx
            except Exception as exc:
                set_span_error(exc)
                raise


# ---------------------------------------------------------------------------
# Top-level context manager
# ---------------------------------------------------------------------------


@contextmanager
def conversation(
    *,
    id: UUID,
    agent: str,
    model: str,
    tags: dict[str, str] | None = None,
) -> Iterator[ConversationContext]:
    """Open a root conversation span.

    Parameters
    ----------
    id:
        Unique conversation identifier.
    agent:
        Name of the agent that owns this conversation.
    model:
        Primary LLM model used in this conversation.
    tags:
        Optional key-value tags for filtering/grouping.

    Yields
    ------
    ConversationContext
        An object with helpers to record system prompts, user messages,
        LLM generations, and tool calls as child spans.

    Example::

        with ytrace.conversation(id=uuid4(), agent="my-agent", model="gpt-4o") as chat:
            chat.system(persona="You are helpful.", tools=tool_specs)
            chat.user("What is Bitcoin price?")
            with chat.llm_gen() as gen:
                ...
    """
    attrs: dict[str, str | list[str]] = {
        ATTR_CONVERSATION_ID: str(id),
        ATTR_AGENT: agent,
        ATTR_CONVERSATION_MODEL: model,
    }
    if tags is not None:
        # Flatten dict tags to a list of "key=value" strings for OTEL
        attrs[ATTR_CONVERSATION_TAGS] = [f"{k}={v}" for k, v in tags.items()]

    tracer = trace.get_tracer("yuutrace")
    with tracer.start_as_current_span(
        "conversation",
        attributes=attrs,  # type: ignore[arg-type]
    ) as span:
        ctx = ConversationContext(span, tracer)
        try:
            yield ctx
        except Exception as exc:
            set_span_error(exc)
            raise
