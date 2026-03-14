from __future__ import annotations

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


def test_tool_span_records_name_and_output() -> None:
    exporter = _make_exporter()

    with ytrace.conversation(id=uuid.uuid4(), agent="a", model="m") as chat:
        with chat.tools() as tools:
            with tools.tool(name="my_tool", call_id="tc_1", input={"x": 1}) as ts:
                ts.ok("result_value")

    spans = exporter.get_finished_spans()
    tool_spans = [s for s in spans if s.name == "tool:my_tool"]
    assert tool_spans, [s.name for s in spans]
    assert tool_spans[0].attributes.get("yuu.tool.name") == "my_tool"
    assert tool_spans[0].attributes.get("yuu.tool.call_id") == "tc_1"
    assert '"result_value"' in (tool_spans[0].attributes.get("yuu.tool.output") or "")


def test_tool_span_records_error() -> None:
    exporter = _make_exporter()

    with ytrace.conversation(id=uuid.uuid4(), agent="a", model="m") as chat:
        with chat.tools() as tools:
            with tools.tool(name="bad_tool", call_id="tc_2", input={}) as ts:
                ts.fail("something went wrong")

    spans = exporter.get_finished_spans()
    tool_spans = [s for s in spans if s.name == "tool:bad_tool"]
    assert tool_spans
    assert tool_spans[0].attributes.get("yuu.tool.error") == "something went wrong"


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

    with ytrace.conversation(id=conv_id, agent="a", model="m") as chat:
        with chat.llm_gen() as gen:
            gen.log([{"type": "text", "text": "hi"}])
        with chat.tools() as tools:
            with tools.tool(name="noop", call_id="tc_1", input={}) as ts:
                ts.ok("ok")

    spans = exporter.get_finished_spans()
    cid = str(conv_id)
    for span in spans:
        if span.name in ("llm_gen", "tools", "tool:noop"):
            assert span.attributes.get("yuu.conversation.id") == cid, (
                f"span {span.name} missing conversation_id"
            )


def test_start_llm_gen_manual_end() -> None:
    """start_llm_gen() returns a context that must be manually ended."""
    exporter = _make_exporter()

    with ytrace.conversation(id=uuid.uuid4(), agent="a", model="m") as chat:
        gen = chat.start_llm_gen()
        gen.log([{"type": "text", "text": "hello"}])
        gen.end()

    spans = exporter.get_finished_spans()
    llm_spans = [s for s in spans if s.name == "llm_gen"]
    assert llm_spans


def test_init_memory(_fresh_tracer_provider) -> None:
    """init_memory() returns a store that captures spans."""
    # init_memory sets its own TracerProvider, so we need a fresh one
    store = ytrace.init_memory()

    conv_id = uuid.uuid4()
    with ytrace.conversation(id=conv_id, agent="test-agent", model="test-model") as chat:
        with chat.llm_gen() as gen:
            gen.log([{"type": "text", "text": "hello"}])
        with chat.tools() as tools:
            with tools.tool(name="echo", call_id="tc_1", input={"msg": "hi"}) as ts:
                ts.ok("hi")

    # Query the store
    all_spans = store.get_all_spans()
    assert len(all_spans) >= 3  # conversation, llm_gen, tools, tool:echo

    conv = store.get_conversation(str(conv_id))
    assert conv is not None
    assert conv["agent"] == "test-agent"

    convs = store.list_conversations()
    assert convs["total"] >= 1
