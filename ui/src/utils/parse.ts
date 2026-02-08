/**
 * Attribute key extraction utilities.
 *
 * This is the ONLY place in the frontend that references yuu.* magic strings.
 * All keys correspond to Python-side otel.py constants.
 */

import type {
  CostEvent,
  LlmUsageEvent,
  Span,
  SpanEvent,
  ToolUsageEvent,
} from "../types";

// ---------------------------------------------------------------------------
// Single-event extractors
// ---------------------------------------------------------------------------

function parseCostEvent(ev: SpanEvent): CostEvent | null {
  const a = ev.attributes;
  const amount = a["yuu.cost.amount"];
  if (amount == null) return null;
  return {
    category: (a["yuu.cost.category"] as "llm" | "tool") ?? "llm",
    currency: (a["yuu.cost.currency"] as string) ?? "USD",
    amount: Number(amount),
    source: a["yuu.cost.source"] as string | undefined,
    pricingId: a["yuu.cost.pricing_id"] as string | undefined,
    llmProvider: a["yuu.llm.provider"] as string | undefined,
    llmModel: a["yuu.llm.model"] as string | undefined,
    llmRequestId: a["yuu.llm.request_id"] as string | undefined,
    toolName: a["yuu.tool.name"] as string | undefined,
    toolCallId: a["yuu.tool.call_id"] as string | undefined,
  };
}

function parseLlmUsageEvent(ev: SpanEvent): LlmUsageEvent | null {
  const a = ev.attributes;
  const provider = a["yuu.llm.provider"];
  if (provider == null) return null;
  return {
    provider: String(provider),
    model: String(a["yuu.llm.model"] ?? ""),
    requestId: a["yuu.llm.request_id"] as string | undefined,
    inputTokens: Number(a["yuu.llm.usage.input_tokens"] ?? 0),
    outputTokens: Number(a["yuu.llm.usage.output_tokens"] ?? 0),
    cacheReadTokens: Number(a["yuu.llm.usage.cache_read_tokens"] ?? 0),
    cacheWriteTokens: Number(a["yuu.llm.usage.cache_write_tokens"] ?? 0),
    totalTokens:
      a["yuu.llm.usage.total_tokens"] != null
        ? Number(a["yuu.llm.usage.total_tokens"])
        : undefined,
  };
}

function parseToolUsageEvent(ev: SpanEvent): ToolUsageEvent | null {
  const a = ev.attributes;
  const name = a["yuu.tool.name"];
  if (name == null) return null;
  return {
    name: String(name),
    callId: a["yuu.tool.call_id"] as string | undefined,
    unit: String(a["yuu.tool.usage.unit"] ?? ""),
    quantity: Number(a["yuu.tool.usage.quantity"] ?? 0),
  };
}

// ---------------------------------------------------------------------------
// Span-level extractors
// ---------------------------------------------------------------------------

/** Extract all cost events from a span's events. */
export function extractCostEvents(span: Span): CostEvent[] {
  return span.events
    .filter((e) => e.name === "yuu.cost")
    .map(parseCostEvent)
    .filter((e): e is CostEvent => e !== null);
}

/** Extract all LLM usage events from a span's events. */
export function extractLlmUsageEvents(span: Span): LlmUsageEvent[] {
  return span.events
    .filter((e) => e.name === "yuu.llm.usage")
    .map(parseLlmUsageEvent)
    .filter((e): e is LlmUsageEvent => e !== null);
}

/** Extract all tool usage events from a span's events. */
export function extractToolUsageEvents(span: Span): ToolUsageEvent[] {
  return span.events
    .filter((e) => e.name === "yuu.tool.usage")
    .map(parseToolUsageEvent)
    .filter((e): e is ToolUsageEvent => e !== null);
}

// ---------------------------------------------------------------------------
// Conversation-level aggregation
// ---------------------------------------------------------------------------

/** Parse all typed events from a list of spans. */
export function parseConversation(spans: Span[]): {
  costs: CostEvent[];
  usages: LlmUsageEvent[];
  toolUsages: ToolUsageEvent[];
} {
  const costs: CostEvent[] = [];
  const usages: LlmUsageEvent[] = [];
  const toolUsages: ToolUsageEvent[] = [];

  for (const span of spans) {
    costs.push(...extractCostEvents(span));
    usages.push(...extractLlmUsageEvents(span));
    toolUsages.push(...extractToolUsageEvents(span));
  }

  return { costs, usages, toolUsages };
}
