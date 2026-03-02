import { useState } from "react";
import { toast } from "sonner";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { CopyableText } from "@/components/copyable-text";
import { JsonViewer } from "@/components/json-viewer";
import { useIndicatorDetail, useEnrichAlert, usePatchIndicator } from "@/hooks/use-api";
import { relativeTime, maliceColor } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  RefreshCw,
  ChevronDown,
  ChevronRight,
  CheckCircle,
  XCircle,
} from "lucide-react";

const MALICE_OPTIONS = ["Pending", "Benign", "Suspicious", "Malicious"];

interface IndicatorDetailSheetProps {
  indicator: { uuid: string; type: string; value: string; malice: string } | null;
  alertUuid: string;
  onClose: () => void;
}

export function IndicatorDetailSheet({
  indicator,
  alertUuid,
  onClose,
}: IndicatorDetailSheetProps) {
  const { data: detailResp, isLoading } = useIndicatorDetail(
    indicator?.uuid ?? null,
  );
  const enrichAlert = useEnrichAlert();
  const patchIndicator = usePatchIndicator();

  const detail = detailResp?.data ?? null;
  const currentMalice = detail?.malice ?? indicator?.malice ?? "Pending";
  const isAnalystOverride = detail?.malice_source === "analyst";

  function handleReEnrich() {
    enrichAlert.mutate(alertUuid, {
      onSuccess: () =>
        toast.success("Enrichment queued — results will appear shortly"),
      onError: () => toast.error("Failed to queue enrichment"),
    });
  }

  function handleMaliceChange(newMalice: string) {
    if (!indicator) return;
    patchIndicator.mutate(
      { uuid: indicator.uuid, body: { malice: newMalice }, alertUuid },
      {
        onSuccess: () => toast.success(`Malice set to ${newMalice}`),
        onError: () => toast.error("Failed to update malice"),
      },
    );
  }

  function handleResetMalice() {
    if (!indicator) return;
    patchIndicator.mutate(
      { uuid: indicator.uuid, body: { malice: null }, alertUuid },
      {
        onSuccess: () => toast.success("Malice reset to enrichment value"),
        onError: () => toast.error("Failed to reset malice"),
      },
    );
  }

  return (
    <Sheet open={!!indicator} onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        side="right"
        className="sm:max-w-xl w-full overflow-y-auto border-border"
      >
        <SheetHeader className="border-b border-border pb-4">
          <div className="flex items-center gap-2">
            <Badge
              variant="outline"
              className="text-[10px] font-semibold uppercase text-teal border-teal/30 bg-teal/10"
            >
              {indicator?.type}
            </Badge>
            <Select value={currentMalice} onValueChange={handleMaliceChange}>
              <SelectTrigger className={cn("h-6 w-28 text-[10px] border", maliceColor(currentMalice))}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-card border-border">
                {MALICE_OPTIONS.map((m) => (
                  <SelectItem key={m} value={m} className="text-xs">{m}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <SheetTitle className="text-base font-mono break-all pr-8">
            <CopyableText text={indicator?.value ?? ""} mono className="text-sm" />
          </SheetTitle>
          <SheetDescription className="sr-only">
            Indicator detail for {indicator?.value}
          </SheetDescription>
        </SheetHeader>

        <div className="p-4 space-y-5">
          {isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-4 w-48" />
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-24 w-full" />
            </div>
          ) : detail ? (
            <>
              {/* Metadata */}
              <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-dim">
                <span>First seen: {relativeTime(detail.first_seen)}</span>
                <span>Last seen: {relativeTime(detail.last_seen)}</span>
                <span>
                  {detail.is_enriched ? "Enriched" : "Not enriched"}
                </span>
                {isAnalystOverride ? (
                  <span className="flex items-center gap-1.5">
                    <span className="text-amber">Analyst override</span>
                    <button
                      onClick={handleResetMalice}
                      className="text-teal hover:underline"
                    >
                      Reset to enrichment
                    </button>
                  </span>
                ) : (
                  <span>Source: enrichment</span>
                )}
              </div>

              {/* Re-enrich */}
              <Button
                variant="outline"
                size="sm"
                onClick={handleReEnrich}
                disabled={enrichAlert.isPending}
                className="h-7 text-xs text-teal border-teal/30 hover:bg-teal/10"
              >
                <RefreshCw
                  className={cn(
                    "h-3.5 w-3.5 mr-1",
                    enrichAlert.isPending && "animate-spin",
                  )}
                />
                Re-enrich
              </Button>

              {/* Provider cards */}
              {detail.enrichment_results &&
              Object.keys(detail.enrichment_results).length > 0 ? (
                <div className="space-y-3">
                  {Object.entries(detail.enrichment_results).map(
                    ([provider, data]) => (
                      <ProviderCard
                        key={provider}
                        provider={provider}
                        data={data as Record<string, unknown>}
                      />
                    ),
                  )}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-10 text-sm text-dim">
                  <p>No enrichment data</p>
                  <p className="text-xs mt-1">
                    Click Re-enrich to run providers
                  </p>
                </div>
              )}
            </>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function ProviderCard({
  provider,
  data,
}: {
  provider: string;
  data: Record<string, unknown>;
}) {
  const [rawExpanded, setRawExpanded] = useState(false);
  const success = data.success as boolean | undefined;
  const enrichedAt = data.enriched_at as string | null | undefined;
  const extracted = (data.extracted ?? {}) as Record<string, unknown>;
  const raw = data.raw as Record<string, unknown> | null | undefined;

  return (
    <div className="rounded-lg border border-border bg-card">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-foreground">{provider}</span>
          {success === true ? (
            <CheckCircle className="h-3.5 w-3.5 text-teal" />
          ) : success === false ? (
            <XCircle className="h-3.5 w-3.5 text-red-threat" />
          ) : null}
        </div>
        {enrichedAt && (
          <span className="text-[11px] text-dim">
            {relativeTime(enrichedAt)}
          </span>
        )}
      </div>

      <div className="p-4 space-y-3">
        {/* Extracted fields */}
        {Object.keys(extracted).length > 0 ? (
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-xs">
            {Object.entries(extracted).map(([key, val]) => (
              <div key={key} className="contents">
                <dt className="text-dim font-medium">{key}</dt>
                <dd className="text-foreground font-mono break-all">
                  {val === null || val === undefined
                    ? "—"
                    : typeof val === "object"
                      ? JSON.stringify(val)
                      : String(val)}
                </dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="text-xs text-dim">No extracted fields</p>
        )}

        {/* Raw response (collapsible) */}
        {raw && (
          <div>
            <button
              onClick={() => setRawExpanded(!rawExpanded)}
              className="flex items-center gap-1 text-xs text-dim hover:text-foreground transition-colors"
            >
              {rawExpanded ? (
                <ChevronDown className="h-3 w-3" />
              ) : (
                <ChevronRight className="h-3 w-3" />
              )}
              Raw response
            </button>
            {rawExpanded && (
              <div className="mt-2">
                <JsonViewer data={raw} defaultExpanded={1} />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
