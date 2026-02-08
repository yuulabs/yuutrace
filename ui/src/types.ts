// ---------------------------------------------------------------------------
// Core types — aligned with ytrace_spec.md and Python SDK otel.py
// ---------------------------------------------------------------------------

/** Summary of a conversation for list views. */
export interface ConversationSummary {
  id: string;
  agent: string;
  model?: string;
  span_count: number;
  total_cost: number;
  start_time: number;
  end_time: number;
}

/** Full conversation with all spans. */
export interface Conversation {
  id: string;
  agent: string;
  model?: string;
  tags?: string[];
  spans: Span[];
  total_cost?: number;
  start_time: number;
  end_time: number;
}

/** A single OTEL span. */
export interface Span {
  trace_id: string;
  span_id: string;
  parent_span_id?: string | null;
  name: string;
  start_time_unix_nano: number;
  end_time_unix_nano: number;
  status_code: number;
  attributes: Record<string, unknown>;
  events: SpanEvent[];
}

/** A single OTEL span event. */
export interface SpanEvent {
  name: string;
  time_unix_nano: number;
  attributes: Record<string, unknown>;
}

/** Parsed cost event from yuu.cost event attributes. */
export interface CostEvent {
  category: "llm" | "tool";
  currency: string;
  amount: number;
  source?: string;
  pricingId?: string;
  llmProvider?: string;
  llmModel?: string;
  llmRequestId?: string;
  toolName?: string;
  toolCallId?: string;
}

/** Parsed LLM usage event from yuu.llm.usage event attributes. */
export interface LlmUsageEvent {
  provider: string;
  model: string;
  requestId?: string;
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens: number;
  cacheWriteTokens: number;
  totalTokens?: number;
}

/** Parsed tool usage event from yuu.tool.usage event attributes. */
export interface ToolUsageEvent {
  name: string;
  callId?: string;
  unit: string;
  quantity: number;
}
