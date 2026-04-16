import { useState } from "react";
import { cn } from "@/lib/utils";
import { relativeTime } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import {
  ChevronDown,
  ChevronRight,
  Terminal,
  Wrench,
  MessageSquare,
  Shield,
  Gauge,
  AlertTriangle,
} from "lucide-react";
import type { RunEvent } from "@/lib/types";

function formatEventTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
  } catch {
    return "";
  }
}

function ToolCallEvent({ event }: { event: RunEvent }) {
  const [expanded, setExpanded] = useState(false);
  const toolName = event.payload?.tool_name as string | undefined;
  const args = event.payload?.arguments ?? event.payload?.args;

  return (
    <div className="border border-border rounded-md overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-surface/50 transition-colors"
      >
        {expanded ? (
          <ChevronDown className="h-3 w-3 text-dim shrink-0" />
        ) : (
          <ChevronRight className="h-3 w-3 text-dim shrink-0" />
        )}
        <Wrench className="h-3 w-3 text-amber shrink-0" />
        <span className="text-xs font-mono text-amber font-medium truncate">
          {toolName ?? "tool_call"}
        </span>
        <span className="text-[10px] text-muted-foreground ml-auto shrink-0">
          {formatEventTime(event.created_at)}
        </span>
      </button>
      {expanded && args && (
        <div className="px-3 pb-2 border-t border-border">
          <pre className="text-[11px] font-mono text-muted-foreground leading-relaxed overflow-x-auto whitespace-pre-wrap mt-2">
            {typeof args === "string" ? args : JSON.stringify(args, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

function ToolResultEvent({ event }: { event: RunEvent }) {
  const [expanded, setExpanded] = useState(false);
  const result = event.payload?.result ?? event.content;
  const isError = event.payload?.is_error === true;

  return (
    <div className={cn(
      "border rounded-md overflow-hidden ml-4",
      isError ? "border-red-threat/30" : "border-border",
    )}>
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-surface/50 transition-colors"
      >
        {expanded ? (
          <ChevronDown className="h-3 w-3 text-dim shrink-0" />
        ) : (
          <ChevronRight className="h-3 w-3 text-dim shrink-0" />
        )}
        <Terminal className="h-3 w-3 text-dim shrink-0" />
        <span className={cn(
          "text-xs font-mono truncate",
          isError ? "text-red-threat" : "text-dim",
        )}>
          result
        </span>
        <span className="text-[10px] text-muted-foreground ml-auto shrink-0">
          {formatEventTime(event.created_at)}
        </span>
      </button>
      {expanded && result && (
        <div className="px-3 pb-2 border-t border-border">
          <pre className={cn(
            "text-[11px] font-mono leading-relaxed overflow-x-auto whitespace-pre-wrap mt-2",
            isError ? "text-red-threat/80" : "text-muted-foreground",
          )}>
            {typeof result === "string" ? result : JSON.stringify(result, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

function FindingEvent({ event }: { event: RunEvent }) {
  return (
    <div className="border-l-2 border-l-teal border border-border rounded-md px-3 py-2">
      <div className="flex items-center gap-2 mb-1">
        <Shield className="h-3 w-3 text-teal shrink-0" />
        <span className="text-xs font-medium text-teal">Finding</span>
        <span className="text-[10px] text-muted-foreground ml-auto shrink-0">
          {formatEventTime(event.created_at)}
        </span>
      </div>
      <p className="text-xs text-foreground leading-relaxed whitespace-pre-wrap">
        {event.content ?? (event.payload ? JSON.stringify(event.payload, null, 2) : "")}
      </p>
    </div>
  );
}

function BudgetCheckEvent({ event }: { event: RunEvent }) {
  const cost = event.payload?.total_cost_cents as number | undefined;
  const budget = event.payload?.budget_cents as number | undefined;

  return (
    <div className="flex items-center gap-2 px-2 py-1">
      <Gauge className="h-3 w-3 text-dim shrink-0" />
      <Badge variant="outline" className="text-[10px] px-1.5 py-0 text-muted-foreground border-border">
        budget check
        {cost !== undefined && (
          <span className="ml-1 text-dim">
            ${(cost / 100).toFixed(2)}
            {budget !== undefined && ` / $${(budget / 100).toFixed(2)}`}
          </span>
        )}
      </Badge>
      <span className="text-[10px] text-muted-foreground ml-auto shrink-0">
        {formatEventTime(event.created_at)}
      </span>
    </div>
  );
}

function AssistantEvent({ event }: { event: RunEvent }) {
  return (
    <div className="px-1 py-1.5">
      <div className="flex items-start gap-2">
        <MessageSquare className="h-3 w-3 text-teal-light mt-0.5 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-xs text-foreground leading-relaxed whitespace-pre-wrap">
            {event.content}
          </p>
          <span className="text-[10px] text-muted-foreground mt-0.5 block">
            {relativeTime(event.created_at)}
          </span>
        </div>
      </div>
    </div>
  );
}

function StderrEvent({ event }: { event: RunEvent }) {
  return (
    <div className="px-2 py-1.5 bg-red-threat/5 rounded-md border border-red-threat/20">
      <div className="flex items-start gap-2">
        <AlertTriangle className="h-3 w-3 text-red-threat mt-0.5 shrink-0" />
        <pre className="text-[11px] font-mono text-red-threat/80 leading-relaxed whitespace-pre-wrap flex-1 min-w-0">
          {event.content}
        </pre>
      </div>
    </div>
  );
}

function StdoutEvent({ event }: { event: RunEvent }) {
  return (
    <div className="px-2 py-1">
      <pre className="text-[11px] font-mono text-muted-foreground leading-relaxed whitespace-pre-wrap">
        {event.content}
      </pre>
    </div>
  );
}

interface TranscriptEventProps {
  event: RunEvent;
}

export function TranscriptEvent({ event }: TranscriptEventProps) {
  switch (event.event_type) {
    case "tool_call":
      return <ToolCallEvent event={event} />;
    case "tool_result":
      return <ToolResultEvent event={event} />;
    case "finding":
      return <FindingEvent event={event} />;
    case "budget_check":
      return <BudgetCheckEvent event={event} />;
    case "llm_response":
    case "assistant":
      return <AssistantEvent event={event} />;
    case "stderr":
      return <StderrEvent event={event} />;
    case "stdout":
      return <StdoutEvent event={event} />;
    default:
      // Fallback for unknown event types
      return (
        <div className="px-2 py-1">
          <div className="flex items-center gap-2 mb-0.5">
            <Badge variant="outline" className="text-[10px] px-1.5 py-0 text-dim border-border">
              {event.event_type}
            </Badge>
            <span className="text-[10px] text-muted-foreground ml-auto">
              {formatEventTime(event.created_at)}
            </span>
          </div>
          {event.content && (
            <p className="text-xs text-muted-foreground whitespace-pre-wrap">{event.content}</p>
          )}
        </div>
      );
  }
}
