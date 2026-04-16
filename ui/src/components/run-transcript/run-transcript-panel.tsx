import { useState, useEffect, useRef, useCallback } from "react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { cn } from "@/lib/utils";
import { formatDate } from "@/lib/format";
import { useRunEvents, useCancelRun } from "@/hooks/use-api";
import { TranscriptEvent } from "./transcript-event";
import type { RunEvent } from "@/lib/types";
import { toast } from "sonner";
import {
  ArrowDown,
  Loader2,
  XCircle,
  Clock,
  DollarSign,
} from "lucide-react";

const TERMINAL_STATUSES = new Set(["succeeded", "failed", "cancelled", "timed_out"]);

function runStatusBadgeClass(status: string): string {
  switch (status) {
    case "succeeded":
      return "text-teal bg-teal/10 border-teal/30";
    case "failed":
      return "text-red-threat bg-red-threat/10 border-red-threat/30";
    case "cancelled":
      return "text-[#9CA3AF] bg-[#57635F]/30 border-[#57635F]/50";
    case "timed_out":
      return "text-amber bg-amber/10 border-amber/30";
    case "running":
      return "text-teal bg-teal/10 border-teal/30 animate-pulse";
    case "queued":
      return "text-muted-foreground bg-muted/50 border-muted";
    default:
      return "text-dim bg-dim/10 border-dim/30";
  }
}

function formatDuration(startedAt: string | null, finishedAt: string | null): string {
  if (!startedAt) return "--";
  const end = finishedAt ? new Date(finishedAt).getTime() : Date.now();
  const ms = end - new Date(startedAt).getTime();
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms / 60000)}m`;
}

interface RunTranscriptPanelProps {
  runUuid: string;
  runStatus: string;
  runStartedAt?: string | null;
  runFinishedAt?: string | null;
  onClose: () => void;
  onStatusChange?: (newStatus: string) => void;
}

export function RunTranscriptPanel({
  runUuid,
  runStatus,
  runStartedAt,
  runFinishedAt,
  onClose,
  onStatusChange,
}: RunTranscriptPanelProps) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);
  const [currentStatus, setCurrentStatus] = useState(runStatus);
  const scrollRef = useRef<HTMLDivElement>(null);
  const sseRef = useRef<EventSource | null>(null);
  const userScrolledRef = useRef(false);

  const isTerminal = TERMINAL_STATUSES.has(currentStatus);

  // Fetch events for terminal runs
  const { data: eventsData, isLoading: eventsLoading } = useRunEvents(runUuid, {
    enabled: isTerminal,
  });

  // Cancel mutation
  const cancelRun = useCancelRun();

  // Load events from API for terminal runs
  useEffect(() => {
    if (isTerminal && eventsData?.data) {
      setEvents(eventsData.data);
    }
  }, [isTerminal, eventsData]);

  // SSE connection for running runs
  useEffect(() => {
    if (isTerminal || currentStatus === "queued") return;

    const apiKey = localStorage.getItem("calseta_api_key");
    // EventSource does not support custom headers, so we use fetch with ReadableStream
    const abortController = new AbortController();
    setIsStreaming(true);

    async function connectSSE() {
      try {
        const headers: Record<string, string> = {
          Accept: "text/event-stream",
        };
        if (apiKey) {
          headers["Authorization"] = `Bearer ${apiKey}`;
        }
        const response = await fetch(`/v1/runs/${runUuid}/stream`, {
          headers,
          signal: abortController.signal,
        });

        if (!response.ok || !response.body) {
          setIsStreaming(false);
          return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          let dataLine: string | null = null;
          for (const line of lines) {
            if (line.startsWith("data: ")) {
              dataLine = line.slice(6);
            } else if (line === "" && dataLine !== null) {
              // Empty line terminates the event
              try {
                const parsed = JSON.parse(dataLine) as RunEvent;
                setEvents((prev) => {
                  // Deduplicate by seq
                  if (prev.some((e) => e.seq === parsed.seq)) return prev;
                  return [...prev, parsed].sort((a, b) => a.seq - b.seq);
                });
              } catch {
                // Skip malformed events
              }
              dataLine = null;
            }
          }
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        // Connection closed or error - SSE ended
      } finally {
        setIsStreaming(false);
        // When stream ends, the run is likely terminal - update status
        setCurrentStatus((prev) => {
          if (!TERMINAL_STATUSES.has(prev)) return "succeeded";
          return prev;
        });
      }
    }

    connectSSE();

    return () => {
      abortController.abort();
      if (sseRef.current) {
        sseRef.current.close();
        sseRef.current = null;
      }
    };
  }, [runUuid, isTerminal, currentStatus]);

  // Auto-scroll
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events, autoScroll]);

  // Detect user scrolling up
  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    if (!isAtBottom && !userScrolledRef.current) {
      userScrolledRef.current = true;
      setAutoScroll(false);
    }
    if (isAtBottom && userScrolledRef.current) {
      userScrolledRef.current = false;
      setAutoScroll(true);
    }
  }, []);

  function resumeAutoScroll() {
    setAutoScroll(true);
    userScrolledRef.current = false;
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }

  // Sync status prop
  useEffect(() => {
    setCurrentStatus(runStatus);
  }, [runStatus]);

  function handleCancel() {
    cancelRun.mutate(runUuid, {
      onSuccess: () => {
        setCurrentStatus("cancelled");
        setIsStreaming(false);
        onStatusChange?.("cancelled");
        toast.success("Run cancelled");
      },
      onError: (err) => {
        toast.error(err instanceof Error ? err.message : "Failed to cancel run");
      },
    });
    setShowCancelConfirm(false);
  }

  // Compute cost from budget_check events
  const lastBudget = [...events].reverse().find((e) => e.event_type === "budget_check");
  const costCents = lastBudget?.payload?.total_cost_cents as number | undefined;

  return (
    <>
      <Sheet open onOpenChange={(open) => { if (!open) onClose(); }}>
        <SheetContent
          side="right"
          className="w-full sm:max-w-xl md:max-w-2xl flex flex-col p-0 gap-0 bg-[#0a0e13]"
          showCloseButton={false}
        >
          {/* Header */}
          <SheetHeader className="px-4 pt-4 pb-3 border-b border-border shrink-0">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <SheetTitle className="text-sm font-heading font-semibold text-foreground">
                  Run Transcript
                </SheetTitle>
                <span className="font-mono text-[11px] text-dim">
                  #{runUuid.slice(-6)}
                </span>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={onClose}
                className="h-7 w-7 p-0 text-dim hover:text-foreground"
              >
                <XCircle className="h-4 w-4" />
              </Button>
            </div>
            <SheetDescription className="sr-only">
              Live transcript of run events
            </SheetDescription>

            {/* Status row */}
            <div className="flex items-center gap-3 mt-2">
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Badge
                      variant="outline"
                      className={cn("text-xs", runStatusBadgeClass(currentStatus))}
                    >
                      {isStreaming && currentStatus === "running" && (
                        <span className="inline-block h-1.5 w-1.5 rounded-full bg-teal animate-pulse mr-1" />
                      )}
                      {currentStatus}
                    </Badge>
                  </TooltipTrigger>
                  <TooltipContent className="bg-card border-border">
                    <p className="text-xs">{currentStatus === "running" ? "Agent is actively processing" : `Run ${currentStatus}`}</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>

              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                      <Clock className="h-3 w-3" />
                      {formatDuration(runStartedAt ?? null, isTerminal ? (runFinishedAt ?? null) : null)}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent className="bg-card border-border">
                    <div className="text-xs space-y-0.5">
                      <p>Started: {runStartedAt ? formatDate(runStartedAt) : "--"}</p>
                      <p>Finished: {runFinishedAt ? formatDate(runFinishedAt) : "--"}</p>
                    </div>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>

              {costCents !== undefined && (
                <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                  <DollarSign className="h-3 w-3" />
                  ${(costCents / 100).toFixed(2)}
                </span>
              )}

              {currentStatus === "running" && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowCancelConfirm(true)}
                  disabled={cancelRun.isPending}
                  className="ml-auto h-7 text-xs border-red-threat/30 text-red-threat hover:bg-red-threat/10 hover:text-red-threat"
                >
                  {cancelRun.isPending ? (
                    <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                  ) : (
                    <XCircle className="h-3 w-3 mr-1" />
                  )}
                  Cancel
                </Button>
              )}
            </div>
          </SheetHeader>

          {/* Event stream */}
          <div
            ref={scrollRef}
            onScroll={handleScroll}
            className="flex-1 overflow-y-auto px-4 py-3 space-y-2"
          >
            {eventsLoading && isTerminal && (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-5 w-5 animate-spin text-dim" />
              </div>
            )}

            {!eventsLoading && events.length === 0 && isTerminal && (
              <div className="text-center text-sm text-dim py-12">
                No events recorded for this run.
              </div>
            )}

            {!eventsLoading && events.length === 0 && !isTerminal && (
              <div className="text-center text-sm text-dim py-12">
                {isStreaming ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="inline-block h-2 w-2 rounded-full bg-teal animate-pulse" />
                    Waiting for events...
                  </span>
                ) : (
                  "Connecting to event stream..."
                )}
              </div>
            )}

            {events.map((event) => (
              <TranscriptEvent key={event.seq} event={event} />
            ))}

            {isStreaming && events.length > 0 && (
              <div className="flex items-center gap-2 px-2 py-1">
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-teal animate-pulse" />
                <span className="text-[11px] text-dim">Streaming...</span>
              </div>
            )}
          </div>

          {/* Auto-scroll resume button */}
          {!autoScroll && events.length > 0 && (
            <div className="absolute bottom-4 right-8">
              <Button
                variant="outline"
                size="sm"
                onClick={resumeAutoScroll}
                className="h-8 text-xs bg-card border-border shadow-md"
              >
                <ArrowDown className="h-3 w-3 mr-1" />
                Jump to latest
              </Button>
            </div>
          )}
        </SheetContent>
      </Sheet>

      <ConfirmDialog
        open={showCancelConfirm}
        onOpenChange={setShowCancelConfirm}
        title="Cancel Run"
        description="Are you sure you want to cancel this run? The agent will stop processing."
        confirmLabel="Cancel Run"
        variant="destructive"
        onConfirm={handleCancel}
      />
    </>
  );
}
