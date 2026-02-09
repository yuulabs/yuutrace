# Agent Guidelines for yuutrace

This document provides coding standards and commands for AI agents working on the yuutrace codebase.

## Project Overview

**yuutrace** is an LLM-oriented observability SDK built on OpenTelemetry with first-class cost and token usage tracking. It consists of:
- **Python SDK** (`yuutrace`) — instrumentation library + CLI for OTLP collector and web UI
- **React UI** (`@yuutrace/ui`) — trace visualization components

## Build, Lint, and Test Commands

### Python

```bash
# Install dependencies
uv sync

# Run the CLI (check it works)
uv run ytrace --help
uv run ytrace server --help
uv run ytrace ui --help

# Import check (basic smoke test)
uv run python -c "import yuutrace; print(yuutrace.__all__)"

# Run a single Python file
uv run python src/yuutrace/context.py

# Build the package
uv build

# No formal test suite yet — use manual testing with example scripts
```

### TypeScript/React UI

```bash
cd ui

# Install dependencies
npm ci

# Type checking
npm run typecheck

# Build library (for npm distribution)
npm run build:lib

# Build standalone app (for ytrace ui command)
npm run build:app

# Build both
npm run build

# Development server
npm run dev

# Preview production build
npm run preview
```

### Full Build (Python + UI)

```bash
# Build UI and copy to Python package's _static/ directory
bash scripts/build_ui.sh
```

## Code Style Guidelines

### Python

#### Imports
- Use `from __future__ import annotations` at the top of every module for forward references
- Group imports: stdlib → third-party → local (separated by blank lines)
- Use absolute imports from package root: `from .types import CostDelta`
- Import types for type hints: `from typing import Any`
- Prefer `from collections.abc import Iterator` over `typing.Iterator` (Python 3.9+)

Example:
```python
from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import msgspec
from opentelemetry import trace

from .types import CostDelta
from .span import current_span
```

#### Types and Type Hints
- **Always use type hints** for function signatures and class attributes
- Use `msgspec.Struct` for frozen data classes (not `dataclasses` or `pydantic`)
- Mark structs as `frozen=True` for immutability
- Use `str | None` instead of `Optional[str]` (PEP 604 union syntax)
- Use `list[T]` and `dict[K, V]` instead of `List[T]` and `Dict[K, V]`
- Add `py.typed` marker file for library type support

Example:
```python
class CostDelta(msgspec.Struct, frozen=True):
    category: CostCategory
    currency: Currency
    amount: float
    source: str | None = None
```

#### Naming Conventions
- **Modules**: lowercase with underscores (`context.py`, `cost.py`)
- **Classes**: PascalCase (`ConversationContext`, `CostDelta`)
- **Functions/methods**: snake_case (`record_cost`, `current_span`)
- **Constants**: UPPER_SNAKE_CASE (`ATTR_CONVERSATION_ID`, `EVENT_COST`)
- **Private members**: prefix with single underscore (`_span`, `_tracer`)

#### Formatting
- **Line length**: 88 characters (Black default)
- **Indentation**: 4 spaces
- **Quotes**: Double quotes for strings (consistent with Black)
- **Docstrings**: Use triple double-quotes `"""..."""`
- **Docstring style**: NumPy/Google style with sections (Parameters, Returns, Raises, Example)

Example:
```python
def record_cost(
    *,
    category: CostCategory | str,
    currency: Currency | str,
    amount: float,
) -> None:
    """Record an incremental cost event on the current span.

    Parameters
    ----------
    category:
        Cost category ("llm" or "tool").
    currency:
        Currency code (e.g., "USD").
    amount:
        Cost amount as a float.

    Raises
    ------
    NoActiveSpanError
        If there is no active recording span.
    """
```

#### Error Handling
- **Fail fast**: Raise exceptions for invalid states (e.g., `NoActiveSpanError`)
- Use custom exceptions for domain errors
- Catch exceptions in context managers and call `set_span_error(exc)` before re-raising
- Never silently swallow errors

Example:
```python
try:
    yield ctx
except Exception as exc:
    set_span_error(exc)
    raise
```

#### Context Managers
- Use `@contextmanager` decorator for simple context managers
- Always handle exceptions and cleanup properly
- Use `__slots__` for context classes to reduce memory overhead

### TypeScript/React

#### Imports
- Group imports: React → third-party → local types → local components/utils
- Use `type` keyword for type-only imports: `import type { Span } from "../types"`
- Use relative imports with explicit extensions in comments (Vite handles this)

Example:
```typescript
import type { CostEvent, LlmUsageEvent, Span } from "../types";

export function LlmCard({ span, usage, cost }: LlmCardProps) {
```

#### Types
- Define interfaces for all component props
- Use `interface` for object shapes, `type` for unions/aliases
- Export types that are part of the public API
- Use `Record<string, unknown>` for arbitrary JSON objects
- Prefer explicit types over `any`

Example:
```typescript
export interface LlmCardProps {
  span: Span;
  usage?: LlmUsageEvent;
  cost?: CostEvent;
}
```

#### Naming Conventions
- **Components**: PascalCase (`LlmCard`, `ConversationFlow`)
- **Functions/variables**: camelCase (`formatTokens`, `parseCostEvent`)
- **Types/Interfaces**: PascalCase (`CostEvent`, `Span`)
- **Constants**: UPPER_SNAKE_CASE or camelCase depending on scope
- **Files**: PascalCase for components (`LlmCard.tsx`), camelCase for utils (`parse.ts`)

#### Formatting
- **Indentation**: 2 spaces
- **Quotes**: Double quotes for strings
- **Semicolons**: Optional but consistent (project uses them)
- **Line length**: ~80-100 characters

#### React Patterns
- Use functional components with hooks (no class components)
- Export component functions directly: `export function LlmCard(...)`
- Keep components pure and presentational (no data fetching in library components)
- Use inline styles or CSS modules (project uses inline styles)
- Destructure props in function signature

#### Comments
- Use `/** JSDoc */` for exported functions and types
- Use `//` for inline comments
- Document magic strings and attribute keys

Example:
```typescript
/**
 * Attribute key extraction utilities.
 *
 * This is the ONLY place in the frontend that references yuu.* magic strings.
 * All keys correspond to Python-side otel.py constants.
 */
```

## Architecture Patterns

### Python SDK
- **Fast fail**: `current_span()` raises `NoActiveSpanError` if no active span
- **Delta semantics**: All cost/usage data recorded as increments, aggregated at query time
- **Type safety**: Use `msgspec.Struct` for all data types, never raw dicts
- **OTEL alignment**: All attribute keys defined in `otel.py`, never hardcoded elsewhere

### React UI
- **Pure presentation**: Components receive data via props, no built-in fetching
- **Type-safe parsing**: All OTEL attribute extraction in `utils/parse.ts`
- **Single source of truth**: Magic strings (`yuu.*` keys) only in `parse.ts`

## File Organization

```
src/yuutrace/
  __init__.py          # Public API exports
  types.py             # msgspec.Struct data types
  context.py           # conversation(), llm_gen(), tools()
  cost.py              # record_cost(), record_cost_delta()
  usage.py             # record_llm_usage(), record_tool_usage()
  span.py              # current_span(), add_event()
  otel.py              # OTEL attribute keys + serialization
  cli/                 # CLI commands (server, ui)

ui/src/
  types.ts             # TypeScript interfaces
  components/          # React components
  utils/parse.ts       # OTEL attribute extraction
  index.ts             # Library exports
```

## Common Tasks

### Adding a new cost/usage field
1. Update `types.py` (Python) and `types.ts` (TypeScript)
2. Update `otel.py` serialization functions
3. Update `utils/parse.ts` extraction functions
4. Update relevant components to display the new field

### Adding a new component
1. Create `ComponentName.tsx` in `ui/src/components/`
2. Export from `ui/src/index.ts`
3. Add props interface with `export interface ComponentNameProps`
4. Use inline styles for consistency

### Modifying the CLI
1. Edit files in `src/yuutrace/cli/`
2. Test with `uv run ytrace <command>`
3. Rebuild UI if static assets changed: `bash scripts/build_ui.sh`

## Notes for Agents

- **No test suite yet**: Validate changes manually with example scripts
- **Python version**: Requires Python ≥3.12 (project uses 3.14)
- **Node version**: Requires Node.js ≥20
- **Package manager**: Use `uv` for Python, `npm` for Node.js
- **No linters configured**: Follow style guidelines manually
- **Documentation**: Update README.md for user-facing changes, this file for agent guidelines
