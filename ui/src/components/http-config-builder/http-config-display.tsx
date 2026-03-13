import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { HttpConfig, HttpStep } from "./types";
import { parseHttpConfig, METHOD_COLORS } from "./types";
import type { HttpMethod } from "./types";
import { TemplatePills } from "./template-input";

interface HttpConfigDisplayProps {
  config: Record<string, unknown>;
}

function KvList({ label, data }: { label: string; data: Record<string, string> }) {
  const entries = Object.entries(data);
  if (entries.length === 0) return null;
  return (
    <div className="mt-1.5">
      <p className="text-[10px] text-dim uppercase tracking-wide mb-0.5">{label}</p>
      <div className="space-y-0.5">
        {entries.map(([k, v]) => (
          <div key={k} className="flex gap-2 text-[11px] font-mono items-baseline">
            <span className="text-dim shrink-0">{k}:</span>
            <TemplatePills text={v} />
          </div>
        ))}
      </div>
    </div>
  );
}

function StepDisplay({ step, index }: { step: HttpStep; index: number }) {
  const method = (step.method || "GET") as HttpMethod;
  return (
    <div className="border border-border rounded-md px-3 py-2">
      {/* Step header */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[11px] text-dim font-mono">#{index + 1}</span>
        <Badge
          variant="outline"
          className={cn("text-[10px] px-1.5 py-0 h-4 font-mono", METHOD_COLORS[method])}
        >
          {method}
        </Badge>
        {step.name && (
          <span className="text-xs text-foreground font-medium">{step.name}</span>
        )}
        {step.optional && (
          <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-4 text-dim border-border">
            optional
          </Badge>
        )}
      </div>

      {/* URL */}
      <div className="mt-1">
        <TemplatePills text={step.url} />
      </div>

      {/* Headers */}
      {step.headers && Object.keys(step.headers).length > 0 && (
        <KvList label="Headers" data={step.headers} />
      )}

      {/* Query params */}
      {step.query_params && Object.keys(step.query_params).length > 0 && (
        <KvList label="Query Params" data={step.query_params} />
      )}

      {/* JSON body */}
      {step.json_body && Object.keys(step.json_body).length > 0 && (
        <div className="mt-1.5">
          <p className="text-[10px] text-dim uppercase tracking-wide mb-0.5">JSON Body</p>
          <pre className="text-[11px] font-mono text-foreground bg-surface/50 rounded px-2 py-1 overflow-x-auto">
            {JSON.stringify(step.json_body, null, 2)}
          </pre>
        </div>
      )}

      {/* Form body */}
      {step.form_body && Object.keys(step.form_body).length > 0 && (
        <KvList label="Form Body" data={step.form_body} />
      )}

      {/* Status / timeout inline */}
      {(step.timeout_seconds || step.expected_status || step.not_found_status) && (
        <div className="flex gap-3 mt-1.5 flex-wrap">
          {step.timeout_seconds != null && (
            <span className="text-[11px] text-dim">
              Timeout: <span className="text-foreground">{step.timeout_seconds}s</span>
            </span>
          )}
          {step.expected_status && step.expected_status.length > 0 && (
            <span className="text-[11px] text-dim">
              Expected: <span className="text-foreground font-mono">{step.expected_status.join(", ")}</span>
            </span>
          )}
          {step.not_found_status && step.not_found_status.length > 0 && (
            <span className="text-[11px] text-dim">
              Not Found: <span className="text-foreground font-mono">{step.not_found_status.join(", ")}</span>
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export function HttpConfigDisplay({ config }: HttpConfigDisplayProps) {
  const parsed = parseHttpConfig(config);

  if (!parsed || parsed.steps.length === 0) {
    return <p className="text-xs text-dim">No HTTP configuration</p>;
  }

  return (
    <div className="space-y-2">
      {parsed.steps.map((step, i) => (
        <StepDisplay key={i} step={step} index={i} />
      ))}

      {/* URL Templates */}
      {parsed.url_templates_by_type && Object.keys(parsed.url_templates_by_type).length > 0 && (
        <div className="pt-2 border-t border-border">
          <p className="text-[11px] text-dim font-medium mb-1.5">URL Templates by Indicator Type</p>
          <div className="space-y-1">
            {Object.entries(parsed.url_templates_by_type).map(([type, url]) => (
              <div key={type} className="flex items-center gap-2">
                <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-4 text-teal border-teal/30 shrink-0">
                  {type}
                </Badge>
                <TemplatePills text={url} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
