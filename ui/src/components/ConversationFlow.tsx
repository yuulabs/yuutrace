import type { CostEvent, Span } from "../types";
import {
  extractCostEvents,
  extractLlmUsageEvents,
  extractToolUsageEvents,
} from "../utils/parse";
import { LlmCard } from "./LlmCard";
import { ToolCard } from "./ToolCard";

export interface ConversationFlowProps {
  spans: Span[];
}

/**
 * Waterfall-style conversation flow.
 *
 * Renders each span as an LlmCard or ToolCard depending on its name,
 * ordered by start time.
 */
export function ConversationFlow({ spans }: ConversationFlowProps) {
  const sorted = [...spans].sort(
    (a, b) => a.start_time_unix_nano - b.start_time_unix_nano,
  );

  return (
    <div style={styles.container}>
      {sorted.map((span) => {
        const costs = extractCostEvents(span);
        const isLlm = span.name === "llm_gen" || span.name.startsWith("llm");
        const isTool =
          span.name === "tools" || span.name.startsWith("tool:");

        if (isLlm) {
          const usages = extractLlmUsageEvents(span);
          const llmCost = costs.find((c) => c.category === "llm");
          return (
            <LlmCard
              key={span.span_id}
              span={span}
              usage={usages[0]}
              cost={llmCost}
            />
          );
        }

        if (isTool) {
          const toolUsages = extractToolUsageEvents(span);
          const toolCost = costs.find((c) => c.category === "tool");
          return (
            <ToolCard
              key={span.span_id}
              span={span}
              usage={toolUsages[0]}
              cost={toolCost}
            />
          );
        }

        // Generic span (e.g. conversation root)
        return <GenericCard key={span.span_id} span={span} costs={costs} />;
      })}
    </div>
  );
}

function GenericCard({ span, costs }: { span: Span; costs: CostEvent[] }) {
  const totalCost = costs.reduce((s, c) => s + c.amount, 0);
  const durationMs =
    (span.end_time_unix_nano - span.start_time_unix_nano) / 1_000_000;

  // Extract system and user context from conversation span
  const systemPersona = span.attributes["yuu.context.system.persona"] as string | undefined;
  const systemTools = span.attributes["yuu.context.system.tools"] as string | undefined;
  const userContent = span.attributes["yuu.context.user.content"] as string | undefined;

  const hasContext = systemPersona || systemTools || userContent;

  return (
    <div style={styles.card}>
      <div style={styles.cardHeader}>
        <span style={styles.spanName}>{span.name}</span>
        <span style={styles.duration}>{durationMs.toFixed(0)}ms</span>
      </div>

      {hasContext && (
        <div style={styles.contextSection}>
          {systemPersona && (
            <div style={styles.contextBlock}>
              <div style={styles.contextLabel}>System</div>
              <div style={styles.contextContent}>{systemPersona}</div>
            </div>
          )}
          {systemTools && (
            <div style={styles.contextBlock}>
              <div style={styles.contextLabel}>Tools</div>
              <pre style={styles.contextPre}>{systemTools}</pre>
            </div>
          )}
          {userContent && (
            <div style={styles.contextBlock}>
              <div style={styles.contextLabel}>User</div>
              <div style={styles.contextContent}>{userContent}</div>
            </div>
          )}
        </div>
      )}

      {totalCost > 0 && (
        <div style={styles.costLine}>Total: ${totalCost.toFixed(4)}</div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
    padding: 16,
  },
  card: {
    background: "#161b22",
    border: "1px solid #2d333b",
    borderRadius: 8,
    padding: "12px 16px",
  },
  cardHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
  },
  spanName: {
    fontWeight: 600,
    fontSize: 14,
    color: "#e1e4e8",
  },
  duration: {
    fontSize: 12,
    color: "#8b949e",
    fontFamily: "monospace",
  },
  costLine: {
    marginTop: 4,
    fontSize: 12,
    color: "#3fb950",
    fontFamily: "monospace",
  },
  contextSection: {
    marginTop: 12,
    paddingTop: 12,
    borderTop: "1px solid #2d333b",
    display: "flex",
    flexDirection: "column",
    gap: 12,
  },
  contextBlock: {
    display: "flex",
    flexDirection: "column",
    gap: 4,
  },
  contextLabel: {
    fontSize: 11,
    fontWeight: 600,
    color: "#8b949e",
    textTransform: "uppercase",
    letterSpacing: "0.5px",
  },
  contextContent: {
    fontSize: 13,
    color: "#c9d1d9",
    lineHeight: 1.5,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
  },
  contextPre: {
    fontSize: 11,
    color: "#8b949e",
    background: "#0d1117",
    padding: 8,
    borderRadius: 4,
    overflow: "auto",
    maxHeight: 200,
    margin: 0,
  },
};
