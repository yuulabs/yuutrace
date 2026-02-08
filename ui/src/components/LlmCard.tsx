import type { CostEvent, LlmUsageEvent, Span } from "../types";

export interface LlmCardProps {
  span: Span;
  usage?: LlmUsageEvent;
  cost?: CostEvent;
}

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

export function LlmCard({ span, usage, cost }: LlmCardProps) {
  const durationMs =
    (span.end_time_unix_nano - span.start_time_unix_nano) / 1_000_000;

  return (
    <div style={styles.card}>
      <div style={styles.header}>
        <div style={styles.headerLeft}>
          <span style={styles.icon}>🤖</span>
          <span style={styles.name}>{span.name}</span>
        </div>
        <div style={styles.headerRight}>
          {cost && (
            <span style={styles.cost}>${cost.amount.toFixed(4)}</span>
          )}
          <span style={styles.duration}>{durationMs.toFixed(0)}ms</span>
        </div>
      </div>

      {usage && (
        <div style={styles.body}>
          <div style={styles.modelLine}>
            <span style={styles.provider}>{usage.provider}</span>
            <span style={styles.model}>{usage.model}</span>
          </div>
          <div style={styles.tokens}>
            <TokenBadge label="in" value={usage.inputTokens} color="#58a6ff" />
            <TokenBadge label="out" value={usage.outputTokens} color="#d2a8ff" />
            {usage.cacheReadTokens > 0 && (
              <TokenBadge
                label="cache↓"
                value={usage.cacheReadTokens}
                color="#3fb950"
              />
            )}
            {usage.cacheWriteTokens > 0 && (
              <TokenBadge
                label="cache↑"
                value={usage.cacheWriteTokens}
                color="#f0883e"
              />
            )}
            {usage.totalTokens != null && (
              <TokenBadge
                label="total"
                value={usage.totalTokens}
                color="#8b949e"
              />
            )}
          </div>
          {usage.requestId && (
            <div style={styles.requestId}>req: {usage.requestId}</div>
          )}
        </div>
      )}

      {span.status_code === 2 && (
        <div style={styles.error}>⚠ Error</div>
      )}
    </div>
  );
}

function TokenBadge({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <span style={{ ...styles.badge, borderColor: color }}>
      <span style={{ color: "#8b949e", fontSize: 10 }}>{label}</span>{" "}
      <span style={{ color, fontWeight: 600 }}>{formatTokens(value)}</span>
    </span>
  );
}

const styles: Record<string, React.CSSProperties> = {
  card: {
    background: "#161b22",
    border: "1px solid #1f3a5f",
    borderRadius: 8,
    padding: "12px 16px",
    borderLeft: "3px solid #58a6ff",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
  },
  headerLeft: {
    display: "flex",
    alignItems: "center",
    gap: 6,
  },
  headerRight: {
    display: "flex",
    alignItems: "center",
    gap: 10,
  },
  icon: {
    fontSize: 16,
  },
  name: {
    fontWeight: 600,
    fontSize: 14,
    color: "#e1e4e8",
  },
  cost: {
    fontSize: 13,
    color: "#3fb950",
    fontFamily: "monospace",
    fontWeight: 600,
  },
  duration: {
    fontSize: 12,
    color: "#8b949e",
    fontFamily: "monospace",
  },
  body: {
    display: "flex",
    flexDirection: "column",
    gap: 6,
  },
  modelLine: {
    display: "flex",
    gap: 8,
    alignItems: "center",
  },
  provider: {
    fontSize: 12,
    color: "#8b949e",
  },
  model: {
    fontSize: 12,
    color: "#d2a8ff",
    background: "#21262d",
    padding: "1px 6px",
    borderRadius: 4,
    fontFamily: "monospace",
  },
  tokens: {
    display: "flex",
    gap: 6,
    flexWrap: "wrap",
  },
  badge: {
    display: "inline-flex",
    gap: 4,
    alignItems: "center",
    fontSize: 12,
    fontFamily: "monospace",
    padding: "2px 8px",
    borderRadius: 4,
    border: "1px solid",
    background: "#0d1117",
  },
  requestId: {
    fontSize: 11,
    color: "#6e7681",
    fontFamily: "monospace",
  },
  error: {
    marginTop: 6,
    fontSize: 12,
    color: "#f85149",
    fontWeight: 600,
  },
};
