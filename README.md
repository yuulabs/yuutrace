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

## Installation

```bash
# Python SDK
pip install yuutrace

# React components (for embedding in your own dashboard)
npm install @yuutrace/ui
```

## Python SDK Usage

```python
import yuutrace as ytrace
from uuid import uuid4

# 1. Open a conversation span
with ytrace.conversation(id=uuid4(), agent="my-agent", model="gpt-4o") as chat:
    chat.system(persona="You are helpful.", tools=tool_specs)
    chat.user("What is Bitcoin price?")

    # 2. LLM generation
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

    # 3. Tool execution
    with chat.tools() as t:
        results = await t.gather([
            {"tool_call_id": "call_1", "tool": search_fn, "params": {"q": "BTC"}},
        ])
```

### SDK API Reference

**Context managers:**

- `conversation(*, id, agent, model, tags=None)` — root span
- `ConversationContext.llm_gen()` — child span for LLM call
- `ConversationContext.tools()` — child span for tool batch

**Recording functions:**

- `record_cost(*, category, currency, amount, ...)` — cost delta
- `record_cost_delta(cost: CostDelta)` — cost delta from struct
- `record_llm_usage(*, provider, model, input_tokens, output_tokens, ...)` — token usage
- `record_tool_usage(usage: ToolUsageDelta)` — tool usage

**Types:**

- `CostDelta`, `LlmUsageDelta`, `ToolUsageDelta` — frozen msgspec structs
- `CostCategory` — `"llm"` | `"tool"`
- `Currency` — `"USD"`

## CLI

### Collector

Receives OTLP/HTTP JSON and stores to SQLite:

```bash
ytrace server --db ./traces.db --port 4318
```

Configure your OpenTelemetry SDK to export here:

```bash
export OTEL_EXPORTER_OTLP_PROTOCOL=http/json
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

### Web UI

Serves a trace visualization dashboard:

```bash
ytrace ui --db ./traces.db --port 8080
```

REST API endpoints:

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
├── scripts/
│   └── build_ui.sh
└── pyproject.toml
```

## License

MIT
