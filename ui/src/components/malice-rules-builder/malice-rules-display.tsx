import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { MaliceRules, MaliceRule } from "./types";
import { parseMaliceRules, VERDICT_COLORS } from "./types";
import type { MaliceVerdict } from "./types";

interface MaliceRulesDisplayProps {
  rules: Record<string, unknown> | null;
}

function VerdictBadge({ verdict }: { verdict: MaliceVerdict }) {
  return (
    <Badge
      variant="outline"
      className={cn("text-[10px] px-1.5 py-0 h-4", VERDICT_COLORS[verdict])}
    >
      {verdict}
    </Badge>
  );
}

function RuleDisplay({ rule, index }: { rule: MaliceRule; index: number }) {
  const valueDisplay =
    Array.isArray(rule.value)
      ? JSON.stringify(rule.value)
      : String(rule.value);

  return (
    <div className="flex items-center gap-2 text-[11px]">
      <span className="text-dim font-mono w-4 text-center shrink-0">{index + 1}</span>
      <code className="font-mono text-foreground">{rule.field}</code>
      <span className="text-teal font-mono">{rule.operator}</span>
      <code className="font-mono text-amber">{valueDisplay}</code>
      <span className="text-dim">&rarr;</span>
      <VerdictBadge verdict={rule.verdict} />
    </div>
  );
}

export function MaliceRulesDisplay({ rules }: MaliceRulesDisplayProps) {
  const parsed = parseMaliceRules(rules);

  if (!parsed || (parsed.rules.length === 0 && parsed.default_verdict === "Pending" && parsed.not_found_verdict === "Pending")) {
    return <p className="text-xs text-dim">No malice rules configured</p>;
  }

  return (
    <div className="space-y-2">
      {parsed.rules.length > 0 && (
        <div className="space-y-1">
          <p className="text-[10px] text-dim uppercase tracking-wide">
            Rules (first match wins)
          </p>
          {parsed.rules.map((rule, i) => (
            <RuleDisplay key={i} rule={rule} index={i} />
          ))}
        </div>
      )}

      <div className="flex gap-4 pt-1">
        <div>
          <p className="text-[10px] text-dim">Default Verdict</p>
          <VerdictBadge verdict={parsed.default_verdict} />
        </div>
        <div>
          <p className="text-[10px] text-dim">Not Found Verdict</p>
          <VerdictBadge verdict={parsed.not_found_verdict} />
        </div>
      </div>
    </div>
  );
}
