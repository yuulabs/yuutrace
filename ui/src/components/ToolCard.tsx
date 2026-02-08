import type { CostEvent, Span, ToolUsageEvent } from "../types";

export interface ToolCardProps {
  span: Span;
  usage?: ToolUsageEvent;
  cost?: CostEvent;
}

export function ToolCard({ span, usage, cost }: ToolCardProps) {
  const durationMs =
    (span.end_time_unix_nano - span.start_time_unix_nano) / 1_000_000;
  const toolName =
    usage?.name ??
    (span.attributes["yuu.tool.name"] as string | undefined) ??
    span.name;

  return (
    <div style={styles.card}>
      <div style={styles.header}>
        <div style={styles.headerLeft}>
          <span style={styles.icon}>🔧</span>
          <span style={styles.name}>{toolName}</span>
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
          <span style={styles.usageLine}>
            {usage.quantity} {usage.unit}
          </span>
        </div>
      )}

      {span.status_code === 2 && (
        <div style={styles.error}>⚠ Error</div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  card: {
    background: "#161b22",
    border: "1px solid #2d4a2d",
    borderRadius: 8,
    padding: "12px 16px",
    borderLeft: "3px solid #3fb950",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
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
    marginTop: 6,
  },
  usageLine: {
    fontSize: 12,
    color: "#8b949e",
    fontFamily: "monospace",
  },
  error: {
    marginTop: 6,
    fontSize: 12,
    color: "#f85149",
    fontWeight: 600,
  },
};
