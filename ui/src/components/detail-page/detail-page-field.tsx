import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface DetailPageFieldProps {
  label: string;
  value: ReactNode;
  mono?: boolean;
}

export function DetailPageField({ label, value, mono }: DetailPageFieldProps) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-xs text-muted-foreground shrink-0">{label}</span>
      <span
        className={cn(
          "text-xs text-foreground text-right truncate",
          mono && "font-mono",
        )}
      >
        {value}
      </span>
    </div>
  );
}
