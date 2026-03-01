import { useState } from "react";
import { ChevronRight, ChevronDown, Copy, Check } from "lucide-react";
import { cn } from "@/lib/utils";

interface JsonViewerProps {
  data: unknown;
  defaultExpanded?: number;
}

export function JsonViewer({ data, defaultExpanded = 2 }: JsonViewerProps) {
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(JSON.stringify(data, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="relative rounded-lg border border-border bg-[#0a0e14] overflow-auto">
      <div className="absolute top-2 right-2 z-10">
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 rounded px-2 py-1 text-[11px] text-dim hover:text-foreground bg-surface/80 hover:bg-surface-hover transition-colors"
        >
          {copied ? (
            <Check className="h-3 w-3 text-teal" />
          ) : (
            <Copy className="h-3 w-3" />
          )}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <div className="p-4 font-mono text-[13px] leading-relaxed">
        <JsonNode value={data} depth={0} defaultExpanded={defaultExpanded} />
      </div>
    </div>
  );
}

function JsonNode({
  value,
  depth,
  defaultExpanded,
  keyName,
}: {
  value: unknown;
  depth: number;
  defaultExpanded: number;
  keyName?: string;
}) {
  const [expanded, setExpanded] = useState(depth < defaultExpanded);

  if (value === null) {
    return (
      <span>
        {keyName !== undefined && <KeyLabel name={keyName} />}
        <span className="text-dim italic">null</span>
      </span>
    );
  }

  if (typeof value === "boolean") {
    return (
      <span>
        {keyName !== undefined && <KeyLabel name={keyName} />}
        <span className="text-amber">{value ? "true" : "false"}</span>
      </span>
    );
  }

  if (typeof value === "number") {
    return (
      <span>
        {keyName !== undefined && <KeyLabel name={keyName} />}
        <span className="text-teal-light">{value}</span>
      </span>
    );
  }

  if (typeof value === "string") {
    return (
      <span>
        {keyName !== undefined && <KeyLabel name={keyName} />}
        <span className="text-[#7FCAB8]">"{value}"</span>
      </span>
    );
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return (
        <span>
          {keyName !== undefined && <KeyLabel name={keyName} />}
          <span className="text-dim">[]</span>
        </span>
      );
    }

    return (
      <div>
        <span
          className="cursor-pointer select-none inline-flex items-center gap-0.5 hover:text-foreground text-dim"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? (
            <ChevronDown className="h-3 w-3 inline" />
          ) : (
            <ChevronRight className="h-3 w-3 inline" />
          )}
          {keyName !== undefined && <KeyLabel name={keyName} />}
          <span className="text-dim">
            [{expanded ? "" : ` ${value.length} items `}]
          </span>
        </span>
        {expanded && (
          <div className={cn("border-l border-border/40 ml-2 pl-3")}>
            {value.map((item, i) => (
              <div key={i}>
                <JsonNode
                  value={item}
                  depth={depth + 1}
                  defaultExpanded={defaultExpanded}
                />
                {i < value.length - 1 && <span className="text-dim">,</span>}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) {
      return (
        <span>
          {keyName !== undefined && <KeyLabel name={keyName} />}
          <span className="text-dim">{"{}"}</span>
        </span>
      );
    }

    return (
      <div>
        <span
          className="cursor-pointer select-none inline-flex items-center gap-0.5 hover:text-foreground text-dim"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? (
            <ChevronDown className="h-3 w-3 inline" />
          ) : (
            <ChevronRight className="h-3 w-3 inline" />
          )}
          {keyName !== undefined && <KeyLabel name={keyName} />}
          <span className="text-dim">
            {"{"}
            {expanded ? "" : ` ${entries.length} keys `}
            {expanded ? "" : "}"}
          </span>
        </span>
        {expanded && (
          <div className={cn("border-l border-border/40 ml-2 pl-3")}>
            {entries.map(([k, v], i) => (
              <div key={k}>
                <JsonNode
                  keyName={k}
                  value={v}
                  depth={depth + 1}
                  defaultExpanded={defaultExpanded}
                />
                {i < entries.length - 1 && <span className="text-dim">,</span>}
              </div>
            ))}
          </div>
        )}
        {expanded && <span className="text-dim">{"}"}</span>}
      </div>
    );
  }

  return (
    <span>
      {keyName !== undefined && <KeyLabel name={keyName} />}
      <span className="text-foreground">{String(value)}</span>
    </span>
  );
}

function KeyLabel({ name }: { name: string }) {
  return (
    <>
      <span className="text-[#CCD0CF]">"{name}"</span>
      <span className="text-dim">: </span>
    </>
  );
}
