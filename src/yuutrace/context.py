"""High-level context managers for structured tracing.

Provides ``conversation()``, ``ConversationContext.llm_gen()``, and
``ConversationContext.tools()`` -- the recommended entry points for
instrumenting LLM agent workloads.

This module is a *pure span factory* — it creates and annotates OTEL spans
but does NOT execute tools. Callers own the execution model.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import msgspec
from opentelemetry import trace

from .init import require_initialized
from .otel import (
    ATTR_AGENT,
    ATTR_CONTEXT_SYSTEM_PERSONA,
    ATTR_CONTEXT_SYSTEM_TOOLS,
    ATTR_CONVERSATION_ID,
    ATTR_CONVERSATION_MODEL,
    ATTR_CONVERSATION_TAGS,
    ATTR_LLM_GEN_ITEMS,
)
from .span import set_span_error

_tracer = trace.get_tracer("yuutrace")


# ---------------------------------------------------------------------------
# ToolSpan
# ---------------------------------------------------------------------------


class ToolSpan:
    """Write output/error to a tool span. Call end() when done."""

    __slots__ = ("_span",)

    def __init__(self, span: trace.Span) -> None:
        self._span = span

    def ok(self, output: Any) -> None:
        self._span.set_attribute("yuu.tool.output", json.dumps(output, default=str))

    def fail(self, error: str) -> None:
        self._span.set_attribute("yuu.tool.error", error)
        set_span_error(self._span, RuntimeError(error))

    def end(self) -> None:
        self._span.end()


# ---------------------------------------------------------------------------
# LlmGenContext
# ---------------------------------------------------------------------------


class LlmGenContext:
    """Context returned by ``ConversationContext.llm_gen()`` /
    ``ConversationContext.start_llm_gen()``.

    Allows logging the raw LLM response items on the current ``llm_gen`` span.
    """

    __slots__ = ("_span",)

    def __init__(self, span: trace.Span) -> None:
        self._span = span

    def log(self, items: list[Any]) -> None:
        """Attach LLM response items to this span for later inspection.

        Each element is auto-serialized to JSON. Handles ``dict``,
        ``msgspec.Struct``, Pydantic ``BaseModel``, dataclasses, and
        falls back to ``str()``.
        """
        def _jsonable(x: Any) -> Any:
            if x is None or isinstance(x, str | int | float | bool):
                return x
            if isinstance(x, list | tuple):
                return [_jsonable(i) for i in x]
            if isinstance(x, dict):
                return {str(k): _jsonable(v) for k, v in x.items()}
            if hasattr(x, "__struct_fields__"):
                try:
                    return msgspec.to_builtins(x)
                except Exception:
                    pass
            if hasattr(x, "model_dump"):
                try:
                    return x.model_dump()
                except Exception:
                    pass
            if hasattr(x, "__dict__"):
                try:
                    return {
                        str(k): _jsonable(v)
                        for k, v in vars(x).items()
                        if not str(k).startswith("_")
                    }
                except Exception:
                    pass
            return str(x)

        serialized = json.dumps([_jsonable(i) for i in items], ensure_ascii=False)
        self._span.set_attribute(ATTR_LLM_GEN_ITEMS, serialized)

    def end(self, error: Exception | None = None) -> None:
        """End the llm_gen span. Optionally record an error."""
        if error is not None:
            set_span_error(self._span, error)
        self._span.end()


# ---------------------------------------------------------------------------
# ToolsContext
# ---------------------------------------------------------------------------


class ToolsContext:
    """Opens child spans for individual tool calls. Does NOT execute tools."""

    __slots__ = ("_parent_span", "_tracer", "_conversation_id")

    def __init__(self, parent_span: trace.Span, tracer: trace.Tracer, conversation_id: str | None = None) -> None:
        self._parent_span = parent_span
        self._tracer = tracer
        self._conversation_id = conversation_id

    def start_tool(self, *, name: str, call_id: str, input: dict[str, Any]) -> ToolSpan:
        """Open a child span for one tool call. Caller must call span.end()."""
        input_str = json.dumps(input, default=str, ensure_ascii=False)
        attrs: dict[str, str] = {
            "yuu.tool.name": name,
            "yuu.tool.call_id": call_id,
            "yuu.tool.input": input_str,
        }
        if self._conversation_id:
            attrs[ATTR_CONVERSATION_ID] = self._conversation_id
        span = self._tracer.start_span(f"tool:{name}", attributes=attrs)
        return ToolSpan(span)

    @contextmanager
    def tool(self, *, name: str, call_id: str, input: dict[str, Any]) -> Iterator[ToolSpan]:
        """Context manager sugar over start_tool/end."""
        ts = self.start_tool(name=name, call_id=call_id, input=input)
        try:
            yield ts
        except Exception as exc:
            ts.fail(f"{type(exc).__name__}: {exc}")
            raise
        finally:
            ts.end()

    def end(self) -> None:
        """End the tools span."""
        self._parent_span.end()


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
            serialized = json.dumps(tools, default=str, ensure_ascii=False)
            self._span.set_attribute(ATTR_CONTEXT_SYSTEM_TOOLS, serialized)

    def user(self, content: str) -> None:
        """Record a user message as a span event (supports multiple calls)."""
        self._span.add_event("user", {"content": content})

    # -- child contexts ----------------------------------------------------

    @property
    def conversation_id(self) -> str | None:
        """Return the conversation ID from the root span, if set."""
        return self._span.attributes.get(ATTR_CONVERSATION_ID)  # type: ignore[union-attr]

    # -- LLM gen (context manager) -----------------------------------------

    @contextmanager
    def llm_gen(self) -> Iterator[LlmGenContext]:
        """Open a child span for an LLM generation step (auto end)."""
        attrs: dict[str, str] = {}
        cid = self.conversation_id
        if cid:
            attrs[ATTR_CONVERSATION_ID] = cid
        with self._tracer.start_as_current_span("llm_gen", attributes=attrs) as span:
            ctx = LlmGenContext(span)
            try:
                yield ctx
            except Exception as exc:
                set_span_error(span, exc)
                raise

    def start_llm_gen(self) -> LlmGenContext:
        """Open a child span for an LLM generation step (manual end)."""
        attrs: dict[str, str] = {}
        cid = self.conversation_id
        if cid:
            attrs[ATTR_CONVERSATION_ID] = cid
        span = self._tracer.start_span("llm_gen", attributes=attrs)
        return LlmGenContext(span)

    # -- Tools (context manager) -------------------------------------------

    @contextmanager
    def tools(self) -> Iterator[ToolsContext]:
        """Open a child span for a batch of tool calls (auto end)."""
        attrs: dict[str, str] = {}
        cid = self.conversation_id
        if cid:
            attrs[ATTR_CONVERSATION_ID] = cid
        with self._tracer.start_as_current_span("tools", attributes=attrs) as span:
            ctx = ToolsContext(span, self._tracer, cid)
            try:
                yield ctx
            except Exception as exc:
                set_span_error(span, exc)
                raise

    def start_tools(self) -> ToolsContext:
        """Open a child span for a batch of tool calls (manual end)."""
        attrs: dict[str, str] = {}
        cid = self.conversation_id
        if cid:
            attrs[ATTR_CONVERSATION_ID] = cid
        span = self._tracer.start_span("tools", attributes=attrs)
        return ToolsContext(span, self._tracer, cid)


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
    """
    attrs: dict[str, str | list[str]] = {
        ATTR_CONVERSATION_ID: str(id),
        ATTR_AGENT: agent,
        ATTR_CONVERSATION_MODEL: model,
    }
    if tags is not None:
        attrs[ATTR_CONVERSATION_TAGS] = [f"{k}={v}" for k, v in tags.items()]

    require_initialized()
    tracer = trace.get_tracer("yuutrace")
    with tracer.start_as_current_span(
        "conversation",
        attributes=attrs,  # type: ignore[arg-type]
    ) as span:
        ctx = ConversationContext(span, tracer)
        try:
            yield ctx
        except Exception as exc:
            set_span_error(span, exc)
            raise
