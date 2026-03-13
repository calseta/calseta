import { Badge } from "@/components/ui/badge";
import { Cpu, KeyRound, Plug } from "lucide-react";

interface ActorBadgeProps {
  actorType: string;
  actorKeyPrefix: string | null;
}

export function ActorBadge({ actorType, actorKeyPrefix }: ActorBadgeProps) {
  switch (actorType) {
    case "system":
      return (
        <Badge variant="outline" className="text-[11px] text-teal bg-teal/10 border-teal/30 gap-1">
          <Cpu className="h-2.5 w-2.5" />
          system
        </Badge>
      );
    case "api":
      return (
        <Badge variant="outline" className="text-[11px] text-foreground border-border gap-1">
          <KeyRound className="h-2.5 w-2.5" />
          {actorKeyPrefix ? <span className="font-mono">{actorKeyPrefix}</span> : "api"}
        </Badge>
      );
    case "mcp":
      return (
        <Badge variant="outline" className="text-[11px] text-teal-light bg-teal-light/5 border-teal-light/30 gap-1">
          <Plug className="h-2.5 w-2.5" />
          {actorKeyPrefix ? <span className="font-mono">{actorKeyPrefix}</span> : "mcp"}
        </Badge>
      );
    default:
      return (
        <Badge variant="outline" className="text-[11px] text-dim border-border">
          {actorType}
        </Badge>
      );
  }
}
