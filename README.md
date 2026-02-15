# yuutrace

LLM-oriented observability SDK built on OpenTelemetry. Provides structured tracing for LLM agent workloads with first-class cost and token usage tracking.

## What's in the box

| Deliverable | Registry | Description |
|---|---|---|
| `yuutrace` | PyPI | Python SDK for instrumentation + CLI (`ytrace server` / `ytrace ui`) |
| `@yuutrace/ui` | npm | React component library for trace visualization |

```
your-agent (Python)
  │  import yuutrace
  │
  ▼
ytrace server ──OTLP/HTTP JSON──▶ SQLite
  │
  ▼
ytrace ui ──REST API──▶ Browser (@yuutrace/ui)
```

## Installation

```bash
# Python SDK (includes CLI tools)
pip install yuutrace

# React components (for embedding in your own dashboard)
npm install @yuutrace/ui
```

## Quick Start

### 1. Start the Trace Collector

```bash
ytrace server --db ./traces.db --port 4318
```

### 2. Initialize Tracing

```python
import yuutrace as ytrace

ytrace.init(service_name="my-agent")
```

If you already configure OpenTelemetry elsewhere, yuutrace reuses the existing `TracerProvider` and `init()` becomes a no-op.

### 3. Instrument Your Agent

Below is a minimal but complete example covering the core workflow: conversation → LLM generation → tool execution.

```python
import yuutrace as ytrace
from uuid import uuid4

ytrace.init(service_name="my-agent")

async def agent_turn(user_msg: str):
    with ytrace.conversation(
        id=uuid4(),            # UUID – unique conversation identifier
        agent="my-agent",      # str  – agent name
        model="gpt-4o",        # str  – primary model
        tags={"env": "prod"},  # dict[str, str] | None – filtering tags
    ) as chat:

        # Record context
        chat.system(persona="You are helpful.", tools=tool_specs)
        chat.user(user_msg)

        # ── LLM generation ──────────────────────────────────────
        with chat.llm_gen() as gen:
            response = await llm.call(messages)

            # Log response items for UI inspection
            gen.log(response.choices[0].message.content)

            # Record token usage (keyword args)
            ytrace.record_llm_usage(
                provider="openai",
                model="gpt-4o",
                input_tokens=150,
                output_tokens=42,
                cache_read_tokens=80,
            )

            # Record cost
            ytrace.record_cost(
                category="llm",        # "llm" | "tool"
                currency="USD",        # "USD"
                amount=0.0023,
                llm_provider="openai",
                llm_model="gpt-4o",
            )

        # ── Tool execution ──────────────────────────────────────
        with chat.tools() as t:
            results = await t.gather([
                {
                    "tool_call_id": "call_1",   # str  – unique call ID
                    "tool": search_fn,           # Callable – sync or async
                    "params": {"q": "BTC"},      # dict – keyword args
                },
            ])
            # results: list[ToolResult]
            # ToolResult.tool_call_id: str
            # ToolResult.output: Any
            # ToolResult.error: str | None
```

### 4. View Traces

```bash
ytrace ui --db ./traces.db --port 8080
# Open http://localhost:8080
```

## `gen.log()` — Logging LLM Response Items

`gen.log(items)` attaches the LLM response to the current `llm_gen` span so you can inspect it in the web UI.

### Signature

```python
LlmGenContext.log(items: list[Any]) -> None
```

### UI-recognised item types

The web UI renders **two** item shapes.  Items with other `type` values are stored but **not rendered**.

| `type` | Required fields | UI rendering |
|---|---|---|
| `"text"` | `text: str` | Text block with pre-wrap whitespace |
| `"tool_calls"` | `tool_calls: [{"function": str, "arguments": Any}, ...]` | Tool call list with function name and arguments |

### Serialization

Each element in the list is auto-serialized to JSON before storage:

| Input type | Serialization method |
|---|---|
| `dict`, `list`, `str`, `int`, `float`, `bool`, `None` | Pass-through |
| `msgspec.Struct` | `msgspec.to_builtins()` |
| Pydantic `BaseModel` | `.model_dump()` |
| `dataclass` | `vars()` (private attrs stripped) |
| Other objects | `str()` fallback |

### Best Practice

```python
# Pattern 1: Log text response (most common)
with chat.llm_gen() as gen:
    response = await client.chat.completions.create(...)
    message = response.choices[0].message
    gen.log([
        {"type": "text", "text": message.content},
    ])

# Pattern 2: Log text + tool-call decisions
with chat.llm_gen() as gen:
    response = await client.chat.completions.create(...)
    message = response.choices[0].message
    gen.log([
        {"type": "text", "text": message.content or ""},
        {"type": "tool_calls", "tool_calls": [
            {"function": tc.function.name,
             "arguments": tc.function.arguments}
            for tc in (message.tool_calls or [])
        ]},
    ])

# Pattern 3: Log msgspec / Pydantic models directly
# (stored as JSON, but only rendered if the serialized dict
#  matches one of the two shapes above)
with chat.llm_gen() as gen:
    gen.log([my_msgspec_struct, my_pydantic_model])
```

### When to call

Call `gen.log()` **once** per `llm_gen()` block, after you have the LLM response. Calling it multiple times overwrites the previous value (it sets a span attribute, not an event).

## Key Concepts

### Span Hierarchy

Every instrumented conversation produces a tree of OpenTelemetry spans:

```
conversation (root)
  ├── llm_gen          # one LLM request
  ├── tools            # a batch of tool calls
  │     ├── tool:search
  │     └── tool:calc
  ├── llm_gen
  └── ...
```

The root `conversation` span carries metadata (`conversation.id`, `agent`, `model`, `tags`). Child spans are created automatically by the context managers.

### Delta Semantics

All cost and usage data is recorded as **increments** (deltas). A single span can emit multiple cost/usage events. Aggregation happens at query time, not write time. This keeps the write path simple and concurrent-safe.

### Event Types

| Event Name | Purpose | Key Attributes |
|---|---|---|
| `yuu.cost` | Cost increment | `category`, `currency`, `amount`, `llm.model`, `tool.name` |
| `yuu.llm.usage` | Token usage | `provider`, `model`, `input_tokens`, `output_tokens`, `cache_read_tokens` |
| `yuu.tool.usage` | Tool usage (optional) | `name`, `unit`, `quantity` |

Business code never writes these event names or attribute keys directly — the SDK wraps them in type-safe functions.

### Fast Fail

`current_span()` raises `NoActiveSpanError` if called outside a span context. No implicit span creation, no silent data loss.

## Python SDK API Reference

### Initialization

```python
ytrace.init(
    *,
    endpoint: str = "http://localhost:4318/v1/traces",
    service_name: str = "yuutrace",
    service_version: str | None = None,
    timeout_seconds: float = 10.0,
) -> None
```

No-op if OpenTelemetry is already configured. Registers `atexit` shutdown hook.

### Context Managers

#### `conversation()`

```python
ytrace.conversation(
    *,
    id: UUID,                            # unique conversation ID
    agent: str,                          # agent name
    model: str,                          # primary LLM model
    tags: dict[str, str] | None = None,  # filtering/grouping tags
) -> Iterator[ConversationContext]
```

Root span.  All recording functions must be called inside this (or a child) context.

#### `ConversationContext`

| Method | Signature | Description |
|---|---|---|
| `system` | `(persona: str, tools: list[Any] \| None = None) -> None` | Record system prompt and tool specs |
| `user` | `(content: str) -> None` | Record user message |
| `llm_gen` | `() -> Iterator[LlmGenContext]` | Open child span for an LLM call |
| `tools` | `() -> Iterator[ToolsContext]` | Open child span for a tool batch |

#### `LlmGenContext`

| Method | Signature | Description |
|---|---|---|
| `log` | `(items: list[Any]) -> None` | Attach LLM response items (auto-serialized to JSON) |

#### `ToolsContext`

| Method | Signature | Description |
|---|---|---|
| `gather` | `(calls: list[dict[str, Any]]) -> list[ToolResult]` | Execute tools concurrently |

Each call dict: `{"tool_call_id": str, "tool": Callable, "params": dict, "name": str (optional)}`.

#### `ToolResult`

```python
class ToolResult(msgspec.Struct, frozen=True):
    tool_call_id: str
    output: Any
    error: str | None = None
```

### Recording Functions

#### `record_llm_usage()`

Accepts either a pre-built struct **or** keyword arguments:

```python
# Keyword args (most common)
ytrace.record_llm_usage(
    provider: str,                       # e.g. "openai", "anthropic"
    model: str,                          # e.g. "gpt-4o", "claude-sonnet-4-20250514"
    request_id: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    total_tokens: int | None = None,     # auto-computed if None
)

# Or pass a struct
ytrace.record_llm_usage(LlmUsageDelta(...))
```

#### `record_cost()` / `record_cost_delta()`

```python
ytrace.record_cost(
    category: str,       # "llm" | "tool"
    currency: str,       # "USD"
    amount: float,       # incremental cost
    # LLM-specific (when category="llm")
    llm_provider: str | None = None,
    llm_model: str | None = None,
    llm_request_id: str | None = None,
    # Tool-specific (when category="tool")
    tool_name: str | None = None,
    tool_call_id: str | None = None,
    # General
    source: str | None = None,
    pricing_id: str | None = None,
)

# Or pass a struct
ytrace.record_cost_delta(CostDelta(...))
```

#### `record_tool_usage()`

```python
ytrace.record_tool_usage(
    ToolUsageDelta(
        name="get_weather",     # tool name
        unit="api_calls",       # unit of measurement
        quantity=1.0,           # amount
        call_id="call_1",       # optional correlation ID
    )
)
```

### Types

All types are frozen `msgspec.Struct` instances (immutable, fast serialization).

| Type | Required Fields | Optional Fields |
|---|---|---|
| `CostDelta` | `category`, `currency`, `amount` | `source`, `pricing_id`, `llm_provider`, `llm_model`, `llm_request_id`, `tool_name`, `tool_call_id` |
| `LlmUsageDelta` | `provider`, `model` | `request_id`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `total_tokens` |
| `ToolUsageDelta` | `name`, `unit`, `quantity` | `call_id` |

Enums:
- `CostCategory` — `"llm"` | `"tool"`
- `Currency` — `"USD"`

### Low-level

| Function | Signature | Description |
|---|---|---|
| `current_span()` | `-> Span` | Return active OTEL span; raises `NoActiveSpanError` if none |
| `add_event()` | `(name: str, attributes: dict) -> None` | Add event to current span (prefer typed wrappers above) |

### Errors

| Error | When |
|---|---|
| `TracingNotInitializedError` | `conversation()` called before `init()` or external OTEL setup |
| `NoActiveSpanError` | Recording function called outside any span context |

## CLI Reference

### `ytrace server`

Receives OTLP/HTTP traces (JSON or Protobuf) and stores them to SQLite.

```bash
ytrace server --db ./traces.db --port 4318 --host 127.0.0.1
```

| Option | Default | Description |
|---|---|---|
| `--db` | `./traces.db` | SQLite database file path |
| `--port` | `4318` | HTTP server port |
| `--host` | `127.0.0.1` | Bind address |

### `ytrace ui`

Serves the trace visualization web UI with REST API.

```bash
ytrace ui --db ./traces.db --port 8080 --host 127.0.0.1
```

| Option | Default | Description |
|---|---|---|
| `--db` | `./traces.db` | SQLite database file path |
| `--port` | `8080` | HTTP server port |
| `--host` | `127.0.0.1` | Bind address |

**REST API endpoints:**

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/conversations` | List conversations (`?limit=50&offset=0&agent=...`) |
| GET | `/api/conversations/{id}` | Single conversation with all spans and events |
| GET | `/api/spans/{id}` | Single span detail |

## React Component Library

`@yuutrace/ui` exports pure presentation components. Data is injected via props — no built-in data fetching, no framework lock-in.

```tsx
import {
  ConversationList,
  ConversationFlow,
  CostSummary,
  UsageSummary,
  SpanTimeline,
  parseConversation,
} from "@yuutrace/ui";

function MyDashboard({ conversation }) {
  const { costs, usages } = parseConversation(conversation.spans);

  return (
    <>
      <SpanTimeline spans={conversation.spans} />
      <ConversationFlow spans={conversation.spans} />
      <CostSummary costs={costs} />
      <UsageSummary usages={usages} />
    </>
  );
}
```

### Components

| Component | Props | Description |
|---|---|---|
| `ConversationList` | `conversations`, `selectedId?`, `onSelect?` | Searchable conversation list |
| `ConversationFlow` | `spans` | Waterfall of LLM/tool cards |
| `LlmCard` | `span`, `usage?`, `cost?` | LLM call detail card |
| `ToolCard` | `span`, `usage?`, `cost?` | Tool call detail card |
| `CostSummary` | `costs` | Cost breakdown by category/model |
| `UsageSummary` | `usages` | Token usage by model |
| `SpanTimeline` | `spans` | Horizontal Gantt chart |

### Utilities

- `parseConversation(spans)` — extract typed cost/usage events from raw spans
- `extractCostEvents(span)` — cost events from a single span
- `extractLlmUsageEvents(span)` — LLM usage from a single span
- `extractToolUsageEvents(span)` — tool usage from a single span

## Examples

See [examples/](examples/) for complete working examples:

- **[weather_agent.py](examples/weather_agent.py)** — Multi-turn agent with LLM calls, tool execution, cost tracking, and error handling

```bash
# Terminal 1: Start collector
ytrace server --db ./traces.db --port 4318

# Terminal 2: Run example
python examples/weather_agent.py

# Terminal 3: Start UI
ytrace ui --db ./traces.db --port 8080
# Open http://localhost:8080
```

## Development

### Prerequisites

- Python >= 3.12
- Node.js >= 20
- [uv](https://docs.astral.sh/uv/) (Python package manager)

### Setup

```bash
# Python
uv sync

# React UI
cd ui && npm install
```

### Build the UI

```bash
# Build standalone app + copy to _static/ for ytrace ui
bash scripts/build_ui.sh

# Or build separately:
cd ui
npm run build:app    # standalone page → dist/app/
npm run build:lib    # npm library → dist/lib/
```

### Project Structure

```
yuutrace/
├── src/yuutrace/
│   ├── __init__.py          # public API
│   ├── types.py             # CostDelta, LlmUsageDelta, ToolUsageDelta
│   ├── context.py           # conversation(), llm_gen(), tools()
│   ├── cost.py              # record_cost(), record_cost_delta()
│   ├── usage.py             # record_llm_usage(), record_tool_usage()
│   ├── span.py              # current_span(), add_event()
│   ├── otel.py              # OTEL attribute keys + serialization
│   └── cli/
│       ├── main.py          # ytrace CLI entry point
│       ├── server.py        # OTLP collector (Starlette)
│       ├── ui.py            # REST API + static serving (Starlette)
│       ├── db.py            # SQLite persistence
│       └── _static/         # pre-built UI assets
├── ui/                      # @yuutrace/ui React package
│   ├── src/
│   │   ├── components/      # ConversationList, LlmCard, etc.
│   │   ├── hooks/           # useTraceData (standalone only)
│   │   ├── pages/           # TracePage
│   │   ├── utils/           # parse.ts
│   │   ├── types.ts
│   │   └── index.ts         # library exports
│   ├── vite.config.ts       # app build
│   └── vite.config.lib.ts   # library build
├── examples/                # Example applications
│   ├── weather_agent.py     # Multi-turn agent example
│   └── README.md            # Example documentation
├── scripts/
│   └── build_ui.sh
└── pyproject.toml
```

## License

MIT
