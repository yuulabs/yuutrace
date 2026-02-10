from __future__ import annotations

import asyncio
import json
import uuid

import msgspec
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import yuutrace as ytrace


def test_tools_context_inferrs_name_from_bound_method_self() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

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
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

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
