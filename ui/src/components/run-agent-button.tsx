import { useState } from "react";
import { toast } from "sonner";
import { Bot, Loader2 } from "lucide-react";
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
import { useAgents, useDispatchAgent } from "@/hooks/use-api";

interface RunAgentButtonProps {
  alertUuid: string;
}

export function RunAgentButton({ alertUuid }: RunAgentButtonProps) {
  const [open, setOpen] = useState(false);
  const { data: agentsResp, isLoading } = useAgents();
  const dispatchAgent = useDispatchAgent();

  const agents = (agentsResp?.data ?? []).filter((a) => a.status === "active");

  function handleSelect(agentUuid: string) {
    const agent = agents.find((a) => a.uuid === agentUuid);
    setOpen(false);
    dispatchAgent.mutate(
      { alertUuid, agentUuid },
      {
        onSuccess: () =>
          toast.success(`Dispatched to ${agent?.name ?? "agent"}`),
        onError: () => toast.error("Failed to dispatch to agent"),
      },
    );
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          disabled={dispatchAgent.isPending}
          className="h-8 text-xs gap-1.5 text-teal border-teal/30 hover:bg-teal/10"
        >
          {dispatchAgent.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Bot className="h-3.5 w-3.5" />
          )}
          Run Agent
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-0 bg-card border-border" align="end" sideOffset={6}>
        <Command>
          <CommandInput placeholder="Search agents..." className="text-xs" />
          <CommandList>
            {isLoading ? (
              <div className="flex items-center justify-center py-6">
                <Loader2 className="h-4 w-4 animate-spin text-dim" />
              </div>
            ) : (
              <>
                <CommandEmpty className="py-6 px-3 text-center text-xs text-dim">
                  No agents found
                </CommandEmpty>
                <CommandGroup>
                  {agents.map((agent) => (
                    <CommandItem
                      key={agent.uuid}
                      value={agent.name}
                      onSelect={() => handleSelect(agent.uuid)}
                      className="cursor-pointer"
                    >
                      <Bot className="h-3.5 w-3.5 text-teal" />
                      <div className="flex flex-col min-w-0">
                        <span className="text-xs font-medium truncate">
                          {agent.name}
                        </span>
                        {agent.description && (
                          <span className="text-[10px] text-dim truncate">
                            {agent.description}
                          </span>
                        )}
                      </div>
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
