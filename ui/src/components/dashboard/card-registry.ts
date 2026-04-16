import type { ComponentType } from "react";

// ---------------------------------------------------------------------------
// Card definition types
// ---------------------------------------------------------------------------

export type CardCategory = "alerts" | "agents" | "workflows" | "platform" | "costs";
export type CardSize = "small" | "wide" | "large";

export interface CardDefinition {
  id: string;
  title: string;
  description: string;
  category: CardCategory;
  size: CardSize;
  /** When true, the card is rendered inline by the dashboard (no separate component file). */
  inline: true;
}

export interface CardDefinitionWithComponent {
  id: string;
  title: string;
  description: string;
  category: CardCategory;
  size: CardSize;
  inline?: false;
  component: ComponentType;
}

export type AnyCardDefinition = CardDefinition | CardDefinitionWithComponent;

// ---------------------------------------------------------------------------
// Size → grid layout mapping
// ---------------------------------------------------------------------------

export const SIZE_TO_GRID: Record<CardSize, { w: number; h: number; minW: number; maxW: number; minH?: number }> = {
  small: { w: 3, h: 1, minW: 2, maxW: 6 },
  wide: { w: 3, h: 2, minW: 2, maxW: 6, minH: 2 },
  large: { w: 6, h: 3, minW: 4, maxW: 12, minH: 2 },
};

// ---------------------------------------------------------------------------
// All card definitions — registered in display order
// ---------------------------------------------------------------------------

export const CARD_REGISTRY: AnyCardDefinition[] = [
  // Control plane widgets
  { id: "cp-queue-depth", title: "Alert Queue", description: "Available alerts in queue and assigned count", category: "agents", size: "wide", inline: true },
  { id: "cp-agent-fleet", title: "Agent Fleet", description: "Active and paused agent count", category: "agents", size: "wide", inline: true },
  { id: "cp-costs-mtd", title: "Spend MTD", description: "Month-to-date total spend in USD", category: "costs", size: "wide", inline: true },
  { id: "cp-pending-actions", title: "Pending Actions", description: "Agent actions requiring human review", category: "agents", size: "wide", inline: true },

  // Platform stats
  { id: "ctx-docs", title: "Knowledge Base", description: "Total knowledge base pages", category: "platform", size: "small", inline: true },
  { id: "det-rules", title: "Detection Rules", description: "Total detection rules configured", category: "platform", size: "small", inline: true },
  { id: "enrich-prov", title: "Enrichment Providers", description: "Active enrichment provider count", category: "platform", size: "small", inline: true },
  { id: "agents", title: "Agents", description: "Total registered agents", category: "agents", size: "small", inline: true },
  { id: "workflows-count", title: "Workflows", description: "Total workflows configured", category: "workflows", size: "small", inline: true },
  { id: "ind-maps", title: "Indicator Mappings", description: "Active indicator field mappings", category: "platform", size: "small", inline: true },

  // Alert KPIs
  { id: "total-alerts", title: "Total Alerts", description: "Total and active alert count", category: "alerts", size: "small", inline: true },
  { id: "mttd", title: "MTTD", description: "Mean Time to Detect", category: "alerts", size: "small", inline: true },
  { id: "mtta", title: "MTTA", description: "Mean Time to Acknowledge", category: "alerts", size: "small", inline: true },
  { id: "mttt", title: "MTTT", description: "Mean Time to Triage", category: "alerts", size: "small", inline: true },
  { id: "mttc", title: "MTTC", description: "Mean Time to Conclusion", category: "alerts", size: "small", inline: true },
  { id: "mtte", title: "MTTE", description: "Mean Time to Enrich", category: "alerts", size: "small", inline: true },

  // Ops KPIs
  { id: "wf-exec", title: "Workflow Executions", description: "Total executions with success rate", category: "workflows", size: "small", inline: true },
  { id: "time-saved", title: "Time Saved", description: "Estimated hours saved via workflows", category: "workflows", size: "small", inline: true },
  { id: "fp-rate", title: "False Positive Rate", description: "False positive rate over last 30 days", category: "alerts", size: "small", inline: true },
  { id: "enrich-cov", title: "Enrichment Coverage", description: "Percentage of alerts enriched", category: "alerts", size: "small", inline: true },
  { id: "pending-approvals", title: "Pending Approvals", description: "Approvals awaiting response", category: "workflows", size: "small", inline: true },

  // Queue KPIs
  { id: "queue-pending", title: "Queue Pending", description: "Pending tasks in queue with in-progress count", category: "platform", size: "small", inline: true },
  { id: "queue-oldest", title: "Oldest Pending Task", description: "Age of the oldest pending task", category: "platform", size: "small", inline: true },

  // Charts
  { id: "sev-chart", title: "Alerts by Severity", description: "Bar chart of alert count by severity level", category: "alerts", size: "large", inline: true },
  { id: "status-chart", title: "Alerts by Status", description: "Bar chart of alert count by status", category: "alerts", size: "large", inline: true },
  { id: "source-chart", title: "Alerts by Source", description: "Bar chart of alert count by source integration", category: "alerts", size: "large", inline: true },
  { id: "provider-type-chart", title: "Enrichment Providers by Type", description: "Bar chart of enrichment providers by indicator type", category: "platform", size: "large", inline: true },
  { id: "queue-health", title: "Queue Health", description: "Stacked bar chart of queue pending/in-progress/failed", category: "platform", size: "large", inline: true },

  // Workflow performance
  { id: "wf-configured", title: "Workflows Configured", description: "Total active workflows", category: "workflows", size: "small", inline: true },
  { id: "wf-success-rate", title: "Workflow Success Rate", description: "Success rate over last 30 days", category: "workflows", size: "small", inline: true },
  { id: "approvals-30d", title: "Approvals (30d)", description: "Approved requests in last 30 days", category: "workflows", size: "small", inline: true },
  { id: "median-approval-time", title: "Median Approval Time", description: "Median response latency for approvals", category: "workflows", size: "small", inline: true },

  // Future agent cards (placeholders)
  { id: "agent-avg-cost", title: "Avg Cost per Alert", description: "Average agent cost per alert investigation", category: "agents", size: "small", inline: true },
  { id: "agent-resolution-rate", title: "Agent Resolution Rate", description: "Percentage of alerts resolved by agents", category: "agents", size: "small", inline: true },
  { id: "agent-avg-time", title: "Avg Investigation Time", description: "Average time agents spend per investigation", category: "agents", size: "small", inline: true },
  { id: "agent-delegation-chart", title: "Agent Delegations", description: "Chart of sub-agent delegation patterns", category: "agents", size: "large", inline: true },
];

// Fast lookup by ID
export const CARD_MAP = new Map(CARD_REGISTRY.map((c) => [c.id, c]));

// ---------------------------------------------------------------------------
// Preset layouts — arrays of card IDs
// ---------------------------------------------------------------------------

export interface DashboardPreset {
  id: string;
  name: string;
  description: string;
  cardIds: string[];
}

export const PRESETS: DashboardPreset[] = [
  {
    id: "soc-overview",
    name: "SOC Overview",
    description: "Full overview of alerts, enrichment, workflows, and platform health",
    cardIds: [
      "cp-queue-depth", "cp-agent-fleet", "cp-costs-mtd", "cp-pending-actions",
      "ctx-docs", "det-rules", "enrich-prov", "agents", "workflows-count", "ind-maps",
      "total-alerts", "mttd", "mtta", "mttt",
      "mttc", "wf-exec", "time-saved", "fp-rate",
      "enrich-cov", "pending-approvals", "queue-pending", "queue-oldest",
      "sev-chart", "status-chart",
      "source-chart", "queue-health",
      "provider-type-chart",
      "wf-configured", "wf-success-rate", "approvals-30d", "median-approval-time", "mtte",
    ],
  },
  {
    id: "agent-operations",
    name: "Agent Operations",
    description: "Agent fleet, costs, queue, and investigation metrics",
    cardIds: [
      "cp-queue-depth", "cp-agent-fleet", "cp-costs-mtd", "cp-pending-actions",
      "agents", "total-alerts", "pending-approvals",
      "agent-avg-cost", "agent-resolution-rate", "agent-avg-time",
      "wf-exec", "wf-success-rate", "time-saved",
      "agent-delegation-chart",
    ],
  },
  {
    id: "minimal",
    name: "Minimal",
    description: "Key metrics at a glance",
    cardIds: [
      "total-alerts", "mttc", "wf-exec", "fp-rate", "enrich-cov",
      "sev-chart",
    ],
  },
];

export const DEFAULT_PRESET_ID = "soc-overview";
export const DEFAULT_CARD_IDS = PRESETS.find((p) => p.id === DEFAULT_PRESET_ID)!.cardIds;
