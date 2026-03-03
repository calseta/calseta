import { useState } from "react";
import { toast } from "sonner";
import { Play, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Badge } from "@/components/ui/badge";
import { useWorkflows, useExecuteWorkflow } from "@/hooks/use-api";

interface RunWorkflowButtonProps {
  indicatorType: string;
  indicatorValue: string;
  alertUuid: string;
}

export function RunWorkflowButton({
  indicatorType,
  indicatorValue,
  alertUuid,
}: RunWorkflowButtonProps) {
  const [open, setOpen] = useState(false);
  const { data: workflowsResp, isLoading } = useWorkflows({ state: "active" });
  const executeWorkflow = useExecuteWorkflow();

  // Filter to workflows that accept this indicator type
  const workflows = (workflowsResp?.data ?? []).filter(
    (w) =>
      w.indicator_types.length === 0 ||
      w.indicator_types.includes(indicatorType),
  );

  function handleSelect(workflowUuid: string) {
    const wf = workflows.find((w) => w.uuid === workflowUuid);
    setOpen(false);
    executeWorkflow.mutate(
      {
        uuid: workflowUuid,
        body: {
          indicator_type: indicatorType,
          indicator_value: indicatorValue,
          alert_uuid: alertUuid,
          trigger_source: "human",
        },
      },
      {
        onSuccess: () =>
          toast.success(`Workflow "${wf?.name ?? "workflow"}" queued`),
        onError: () => toast.error("Failed to execute workflow"),
      },
    );
  }

  const riskColor: Record<string, string> = {
    low: "text-teal border-teal/30",
    medium: "text-amber border-amber/30",
    high: "text-orange-400 border-orange-400/30",
    critical: "text-red-threat border-red-threat/30",
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          disabled={executeWorkflow.isPending}
          className="h-7 text-xs gap-1.5 text-teal border-teal/30 hover:bg-teal/10"
        >
          {executeWorkflow.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Play className="h-3.5 w-3.5" />
          )}
          Run Workflow
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72 p-0 bg-card border-border" align="start">
        <Command>
          <CommandInput placeholder="Search workflows..." className="text-xs" />
          <CommandList>
            {isLoading ? (
              <div className="flex items-center justify-center py-6">
                <Loader2 className="h-4 w-4 animate-spin text-dim" />
              </div>
            ) : (
              <>
                <CommandEmpty className="text-xs text-dim">
                  No matching workflows
                </CommandEmpty>
                <CommandGroup>
                  {workflows.map((wf) => (
                    <CommandItem
                      key={wf.uuid}
                      value={wf.name}
                      onSelect={() => handleSelect(wf.uuid)}
                      className="cursor-pointer"
                    >
                      <Play className="h-3.5 w-3.5 text-teal shrink-0" />
                      <div className="flex flex-col min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          <span className="text-xs font-medium truncate">
                            {wf.name}
                          </span>
                          <Badge
                            variant="outline"
                            className={`text-[9px] px-1 py-0 ${riskColor[wf.risk_level] ?? "text-dim border-border"}`}
                          >
                            {wf.risk_level}
                          </Badge>
                        </div>
                        {wf.documentation && (
                          <span className="text-[10px] text-dim truncate">
                            {wf.documentation}
                          </span>
                        )}
                      </div>
                      {wf.requires_approval && (
                        <span className="text-[9px] text-amber shrink-0">
                          approval
                        </span>
                      )}
                    </CommandItem>
                  ))}
                </CommandGroup>
              </>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
