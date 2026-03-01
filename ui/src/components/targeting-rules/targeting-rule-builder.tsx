import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Plus, X } from "lucide-react";
import {
  type TargetingRule,
  type TargetingRules,
  type TargetingField,
  type TargetingOp,
  FIELD_CONFIGS,
  FIELDS,
  OP_LABELS,
} from "./types";

// ---------------------------------------------------------------------------
// TargetingRuleRow
// ---------------------------------------------------------------------------

function TargetingRuleRow({
  rule,
  onChange,
  onRemove,
}: {
  rule: TargetingRule;
  onChange: (rule: TargetingRule) => void;
  onRemove: () => void;
}) {
  const fieldConfig = FIELD_CONFIGS[rule.field];
  const allowedOps = fieldConfig.allowedOps;

  function handleFieldChange(field: string) {
    const f = field as TargetingField;
    const cfg = FIELD_CONFIGS[f];
    const firstOp = cfg.allowedOps[0];
    const defaultValue = firstOp === "in" ? [] : cfg.valueType === "number" ? 0 : "";
    onChange({ field: f, op: firstOp, value: defaultValue });
  }

  function handleOpChange(op: string) {
    const o = op as TargetingOp;
    // If switching to/from "in", adjust value type
    if (o === "in" && !Array.isArray(rule.value)) {
      onChange({ ...rule, op: o, value: rule.value ? [String(rule.value)] : [] });
    } else if (o !== "in" && Array.isArray(rule.value)) {
      onChange({ ...rule, op: o, value: rule.value[0] ?? "" });
    } else {
      onChange({ ...rule, op: o });
    }
  }

  function renderValueInput() {
    const isMulti = rule.op === "in";

    if (fieldConfig.valueType === "select" && !isMulti) {
      return (
        <Select
          value={String(rule.value)}
          onValueChange={(v) => onChange({ ...rule, value: v })}
        >
          <SelectTrigger className="bg-surface border-border text-xs h-8 w-40">
            <SelectValue placeholder="Select..." />
          </SelectTrigger>
          <SelectContent className="bg-card border-border">
            {fieldConfig.options?.map((opt) => (
              <SelectItem key={opt} value={opt} className="text-xs">
                {opt}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      );
    }

    if (fieldConfig.valueType === "number") {
      return (
        <Input
          type="number"
          min={0}
          max={5}
          value={String(rule.value)}
          onChange={(e) => onChange({ ...rule, value: Number(e.target.value) })}
          className="bg-surface border-border text-xs h-8 w-24"
        />
      );
    }

    // text or multi-value
    if (isMulti) {
      const arr = Array.isArray(rule.value) ? rule.value : [];
      return (
        <Input
          value={arr.join(", ")}
          onChange={(e) => {
            const vals = e.target.value.split(",").map((s) => s.trim()).filter(Boolean);
            onChange({ ...rule, value: vals });
          }}
          placeholder="Comma-separated values"
          className="bg-surface border-border text-xs h-8 flex-1 min-w-32"
        />
      );
    }

    return (
      <Input
        value={String(rule.value)}
        onChange={(e) => onChange({ ...rule, value: e.target.value })}
        placeholder={rule.field === "tags" ? "Tag value" : "Value"}
        className="bg-surface border-border text-xs h-8 flex-1 min-w-32"
      />
    );
  }

  return (
    <div className="flex items-center gap-2">
      <Select value={rule.field} onValueChange={handleFieldChange}>
        <SelectTrigger className="bg-surface border-border text-xs h-8 w-32">
          <SelectValue />
        </SelectTrigger>
        <SelectContent className="bg-card border-border">
          {FIELDS.map((f) => (
            <SelectItem key={f} value={f} className="text-xs">
              {FIELD_CONFIGS[f].label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select value={rule.op} onValueChange={handleOpChange}>
        <SelectTrigger className="bg-surface border-border text-xs h-8 w-28">
          <SelectValue />
        </SelectTrigger>
        <SelectContent className="bg-card border-border">
          {allowedOps.map((op) => (
            <SelectItem key={op} value={op} className="text-xs">
              {OP_LABELS[op]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {renderValueInput()}

      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={onRemove}
        className="h-8 w-8 p-0 text-dim hover:text-red-threat shrink-0"
      >
        <X className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// TargetingRuleSection
// ---------------------------------------------------------------------------

function TargetingRuleSection({
  title,
  description,
  rules,
  onChange,
}: {
  title: string;
  description: string;
  rules: TargetingRule[];
  onChange: (rules: TargetingRule[]) => void;
}) {
  function addRule() {
    onChange([...rules, { field: "source_name", op: "eq", value: "" }]);
  }

  function updateRule(index: number, rule: TargetingRule) {
    const next = [...rules];
    next[index] = rule;
    onChange(next);
  }

  function removeRule(index: number) {
    onChange(rules.filter((_, i) => i !== index));
  }

  return (
    <div className="space-y-2">
      <div>
        <span className="text-xs font-medium text-foreground">{title}</span>
        <span className="text-[11px] text-dim ml-2">{description}</span>
      </div>
      {rules.map((rule, i) => (
        <TargetingRuleRow
          key={i}
          rule={rule}
          onChange={(r) => updateRule(i, r)}
          onRemove={() => removeRule(i)}
        />
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={addRule}
        className="text-xs border-dashed border-border text-dim hover:text-teal hover:border-teal/40"
      >
        <Plus className="h-3 w-3 mr-1" />
        Add Rule
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// TargetingRuleBuilder (exported)
// ---------------------------------------------------------------------------

interface TargetingRuleBuilderProps {
  value: TargetingRules | null;
  onChange: (rules: TargetingRules | null) => void;
}

export function TargetingRuleBuilder({ value, onChange }: TargetingRuleBuilderProps) {
  const rules = value ?? { match_any: [], match_all: [] };

  function handleChange(section: "match_any" | "match_all", sectionRules: TargetingRule[]) {
    const next = { ...rules, [section]: sectionRules };
    if (next.match_any.length === 0 && next.match_all.length === 0) {
      onChange(null);
    } else {
      onChange(next);
    }
  }

  return (
    <div className="space-y-4">
      <TargetingRuleSection
        title="Match Any (OR)"
        description="Alert matches if any of these rules pass"
        rules={rules.match_any}
        onChange={(r) => handleChange("match_any", r)}
      />
      <Separator className="bg-border" />
      <TargetingRuleSection
        title="Match All (AND)"
        description="Alert must match all of these rules"
        rules={rules.match_all}
        onChange={(r) => handleChange("match_all", r)}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// TargetingRuleDisplay (read-only rendering)
// ---------------------------------------------------------------------------

export function TargetingRuleDisplay({ rules }: { rules: Record<string, unknown> | null | undefined }) {
  if (!rules) return <span className="text-xs text-dim">No targeting rules</span>;

  const matchAny = Array.isArray(rules.match_any) ? (rules.match_any as TargetingRule[]) : [];
  const matchAll = Array.isArray(rules.match_all) ? (rules.match_all as TargetingRule[]) : [];

  if (matchAny.length === 0 && matchAll.length === 0) {
    return <span className="text-xs text-dim">No targeting rules</span>;
  }

  function renderRule(rule: TargetingRule, key: number) {
    const fieldLabel = FIELD_CONFIGS[rule.field]?.label ?? rule.field;
    const opLabel = OP_LABELS[rule.op] ?? rule.op;
    const displayValue = Array.isArray(rule.value)
      ? rule.value.join(", ")
      : String(rule.value);

    return (
      <div key={key} className="flex items-center gap-1.5">
        <Badge variant="outline" className="text-[10px] text-teal border-teal/30 font-mono">
          {fieldLabel}
        </Badge>
        <span className="text-[11px] text-dim">{opLabel}</span>
        <Badge variant="outline" className="text-[10px] text-foreground border-border font-mono">
          {displayValue}
        </Badge>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {matchAny.length > 0 && (
        <div className="space-y-1.5">
          <span className="text-[11px] text-dim font-medium">Match Any (OR)</span>
          {matchAny.map((r, i) => renderRule(r, i))}
        </div>
      )}
      {matchAll.length > 0 && (
        <div className="space-y-1.5">
          <span className="text-[11px] text-dim font-medium">Match All (AND)</span>
          {matchAll.map((r, i) => renderRule(r, i))}
        </div>
      )}
    </div>
  );
}
