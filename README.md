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

The collector receives traces from your instrumented application and stores them in SQLite:

```bash
ytrace server --db ./traces.db --port 4318
```

This starts an OTLP/HTTP JSON endpoint at `http://localhost:4318`.

### 2. Configure Your Application

Set up OpenTelemetry to export traces to the collector:

```python
import os
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# IMPORTANT: Set JSON protocol before creating exporter
os.environ["OTEL_EXPORTER_OTLP_TRACES_PROTOCOL"] = "http/json"

# Configure tracer provider
provider = TracerProvider()
otlp_exporter = OTLPSpanExporter(
    endpoint="http://localhost:4318",  # Don't include /v1/traces
)
provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
trace.set_tracer_provider(provider)
```

Or use environment variables:

```bash
export OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/json
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

### 3. Instrument Your Agent Code

Use yuutrace context managers to wrap your agent logic:

```python
import yuutrace as ytrace
from uuid import uuid4

# Open a conversation span
with ytrace.conversation(id=uuid4(), agent="my-agent", model="gpt-4o") as chat:
    chat.system(persona="You are helpful.", tools=tool_specs)
    chat.user("What is Bitcoin price?")

    # LLM generation
    with chat.llm_gen() as gen:
        response = await llm.call(messages)
        gen.log(response.items)

        # Record token usage
        ytrace.record_llm_usage(
            provider="openai",
            model="gpt-4o",
            input_tokens=150,
            output_tokens=42,
        )

        # Record cost
        ytrace.record_cost(
            category="llm",
            currency="USD",
            amount=0.0023,
        )

    # Tool execution
    with chat.tools() as t:
        results = await t.gather([
            {"tool_call_id": "call_1", "tool": search_fn, "params": {"q": "BTC"}},
        ])
```

### 4. View Traces in the Web UI

Start the web UI to visualize collected traces:

```bash
ytrace ui --db ./traces.db --port 8080
```

Open **http://localhost:8080** in your browser. The UI provides:

- **Conversation List** — Browse all collected traces with search and filtering
- **Conversation Flow** — Waterfall view of LLM calls and tool executions
- **Cost Analysis** — Breakdown by category (LLM vs tools) and model
- **Token Usage** — Input/output/cache token metrics for each LLM call
- **Timeline View** — Gantt chart showing operation durations and concurrency
- **Span Details** — Inspect individual spans with full attributes and events

## Examples

Check out the [examples/](examples/) directory for complete working examples:

- **[weather_agent.py](examples/weather_agent.py)** — Multi-turn agent with LLM calls, tool execution, cost tracking, and error handling

To run the example:

```bash
# Terminal 1: Start collector
ytrace server --db ./traces.db --port 4318

# Terminal 2: Run example
python examples/weather_agent.py

# Terminal 3: Start UI
ytrace ui --db ./traces.db --port 8080
# Open http://localhost:8080
```

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

### Context managers

- `conversation(*, id, agent, model, tags=None)` — root span
- `ConversationContext.llm_gen()` — child span for LLM call
- `ConversationContext.tools()` — child span for tool batch

### Recording functions

- `record_cost(*, category, currency, amount, ...)` — cost delta
- `record_cost_delta(cost: CostDelta)` — cost delta from struct
- `record_llm_usage(*, provider, model, input_tokens, output_tokens, ...)` — token usage
- `record_tool_usage(usage: ToolUsageDelta)` — tool usage

### Types

- `CostDelta`, `LlmUsageDelta`, `ToolUsageDelta` — frozen msgspec structs
- `CostCategory` — `"llm"` | `"tool"`
- `Currency` — `"USD"`

## CLI Reference

### `ytrace server`

Receives OTLP/HTTP JSON traces and stores them to SQLite.

```bash
ytrace server --db ./traces.db --port 4318
```

**Options:**
- `--db PATH` — SQLite database file path (default: `./traces.db`)
- `--port PORT` — HTTP server port (default: `4318`)

### `ytrace ui`

Serves the trace visualization web UI with REST API.

```bash
ytrace ui --db ./traces.db --port 8080
```

**Options:**
- `--db PATH` — SQLite database file path (default: `./traces.db`)
- `--port PORT` — HTTP server port (default: `8080`)

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

## Development

### Prerequisites

- Python >= 3.14
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
