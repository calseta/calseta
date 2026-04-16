import { formatDistanceToNow } from "date-fns";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function relativeTime(iso: string): string {
  return formatDistanceToNow(new Date(iso), { addSuffix: true });
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  const mon = MONTHS[d.getUTCMonth()];
  const day = d.getUTCDate();
  const year = d.getUTCFullYear();
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  return `${mon} ${day}, ${year} ${hh}:${mm} UTC`;
}

export function formatSeconds(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return "--";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`;
  return `${(seconds / 86400).toFixed(1)}d`;
}

export function formatPercent(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`;
}

export function severityColor(severity: string): string {
  switch (severity) {
    case "Critical":
      return "text-red-threat bg-red-threat/10 border-red-threat/30";
    case "High":
      return "text-amber bg-amber/10 border-amber/30";
    case "Medium":
      return "text-teal-light bg-teal-light/10 border-teal-light/30";
    case "Low":
      return "text-dim bg-dim/10 border-dim/30";
    case "Informational":
      return "text-muted-foreground bg-muted/50 border-muted";
    default:
      return "text-muted-foreground bg-muted/50 border-muted";
  }
}

export function statusColor(status: string): string {
  switch (status) {
    case "Open":
      return "text-teal bg-teal/10 border-teal/30";
    case "Triaging":
      return "text-amber bg-amber/10 border-amber/30";
    case "Escalated":
      return "text-red-threat bg-red-threat/10 border-red-threat/30";
    case "Closed":
      return "text-dim bg-dim/10 border-dim/30";
    // Agent status values
    case "active":
      return "text-teal bg-teal/10 border-teal/30";
    case "paused":
      return "text-amber bg-amber/10 border-amber/30";
    case "terminated":
      return "text-red-threat bg-red-threat/10 border-red-threat/30";
    default:
      return "text-muted-foreground bg-muted/50 border-muted";
  }
}

export function enrichmentStatusColor(status: string): string {
  switch (status) {
    case "Pending":
      return "text-amber bg-amber/10 border-amber/30";
    case "Enriched":
      return "text-teal bg-teal/10 border-teal/30";
    case "Failed":
      return "text-red-threat bg-red-threat/10 border-red-threat/30";
    default:
      return "text-muted-foreground bg-muted/50 border-muted";
  }
}

export function maliceColor(malice: string): string {
  switch (malice) {
    case "Malicious":
      return "text-red-threat bg-red-threat/10 border-red-threat/30";
    case "Suspicious":
      return "text-amber bg-amber/10 border-amber/30";
    case "Benign":
      return "text-teal bg-teal/10 border-teal/30";
    default:
      return "text-dim bg-dim/10 border-dim/30";
  }
}

export function eventDotColor(eventType: string): string {
  if (eventType.includes("closed")) return "bg-dim";
  if (eventType.includes("note_added")) return "bg-teal-light";
  if (eventType.includes("malice")) return "bg-amber";
  if (eventType.includes("severity")) return "bg-amber";
  if (eventType.includes("finding")) return "bg-teal-light";
  if (eventType.includes("workflow") || eventType.includes("approval")) return "bg-amber";
  if (eventType.includes("enrichment")) return "bg-teal";
  if (eventType.includes("ingested") || eventType.includes("created")) return "bg-teal";
  if (eventType.includes("status")) return "bg-teal-light";
  return "bg-teal";
}

export function riskColor(risk: string): string {
  switch (risk) {
    case "critical":
      return "text-red-threat bg-red-threat/10 border-red-threat/30";
    case "high":
      return "text-amber bg-amber/10 border-amber/30";
    case "medium":
      return "text-teal-light bg-teal-light/10 border-teal-light/30";
    case "low":
      return "text-dim bg-dim/10 border-dim/30";
    default:
      return "text-muted-foreground bg-muted/50 border-muted";
  }
}
