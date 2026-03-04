import { useState } from "react";
import { ChevronRight, ChevronDown, Info } from "lucide-react";
import { TEMPLATE_VARIABLES } from "./types";

export function TemplateHint() {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-border rounded-md overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 w-full px-3 py-1.5 text-[11px] text-dim hover:text-teal transition-colors"
      >
        {expanded ? (
          <ChevronDown className="h-3 w-3 shrink-0" />
        ) : (
          <ChevronRight className="h-3 w-3 shrink-0" />
        )}
        <Info className="h-3 w-3 shrink-0" />
        Template Variables Reference
      </button>
      {expanded && (
        <div className="px-3 pb-2 space-y-1">
          {TEMPLATE_VARIABLES.map((tv) => (
            <div key={tv.variable} className="flex items-baseline gap-2 text-[11px]">
              <code className="font-mono text-teal shrink-0">{tv.variable}</code>
              <span className="text-dim">{tv.description}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
