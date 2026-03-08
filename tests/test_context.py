from __future__ import annotations

import asyncio
import json
import uuid

import msgspec
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import yuutrace as ytrace


@pytest.fixture(autouse=True)
def _fresh_tracer_provider():
    """Give each test its own TracerProvider so they don't interfere."""
    provider = TracerProvider()
    trace.set_tracer_provider(provider)
    yield
    provider.shutdown()


def _make_exporter() -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    provider = trace.get_tracer_provider()
    assert isinstance(provider, TracerProvider)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return exporter


def test_tools_context_infers_name_from_bound_method_self() -> None:
    exporter = _make_exporter()

    class _Spec(msgspec.Struct, frozen=True):
        name: str

    class _Tool:
        spec = _Spec(name="my_tool")

    class _Bound:
        _tool = _Tool()

        async def run(self, x: int) -> str:
            return f"ok:{x}"

    bound = _Bound()

    with ytrace.conversation(id=uuid.uuid4(), agent="a", model="m") as chat:
        with chat.tools() as tools:
            asyncio.run(
                tools.gather(
                    [
                        {
                            "tool_call_id": "tc_1",
                            "tool": bound.run,
                            "params": {"x": 1},
                        }
                    ]
                )
            )

    spans = exporter.get_finished_spans()
    tool_spans = [s for s in spans if s.name == "tool:my_tool"]
    assert tool_spans, [s.name for s in spans]
    assert tool_spans[0].attributes.get("yuu.tool.name") == "my_tool"


def test_llm_gen_log_serializes_msgspec_structs_to_json() -> None:
    exporter = _make_exporter()

    class Item(msgspec.Struct, frozen=True):
        type: str
        value: int

    with ytrace.conversation(id=uuid.uuid4(), agent="a", model="m") as chat:
        with chat.llm_gen() as gen:
            gen.log([Item(type="x", value=1)])

    spans = exporter.get_finished_spans()
    llm_spans = [s for s in spans if s.name == "llm_gen"]
    raw = llm_spans[0].attributes.get("yuu.llm_gen.items")
    assert isinstance(raw, str) and raw
    payload = json.loads(raw)
    assert payload == [{"type": "x", "value": 1}]


def test_conversation_id_propagated_to_child_spans() -> None:
    """Verify conversation_id is set on llm_gen, tools, and tool:* spans."""
    exporter = _make_exporter()
    conv_id = uuid.uuid4()

    class _Bound:
        async def noop(self) -> str:
            return "ok"

    bound = _Bound()

    with ytrace.conversation(id=conv_id, agent="a", model="m") as chat:
        with chat.llm_gen() as gen:
            gen.log([{"type": "text", "text": "hi"}])
        with chat.tools() as tools:
            asyncio.run(
                tools.gather(
                    [{"tool_call_id": "tc_1", "tool": bound.noop, "name": "noop"}]
                )
            )

    spans = exporter.get_finished_spans()
    cid = str(conv_id)
    for span in spans:
        if span.name in ("llm_gen", "tools", "tool:noop"):
            assert span.attributes.get("yuu.conversation.id") == cid, (
                f"span {span.name} missing conversation_id"
            )
