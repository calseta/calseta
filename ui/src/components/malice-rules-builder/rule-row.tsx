import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ArrowUp, ArrowDown, Trash2 } from "lucide-react";
import type { RuleFormState, RuleOperator, MaliceVerdict } from "./types";
import { OPERATORS, VERDICTS } from "./types";

interface RuleRowProps {
  rule: RuleFormState;
  index: number;
  total: number;
  onChange: (rule: RuleFormState) => void;
  onRemove: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
}

export function RuleRow({
  rule,
  index,
  total,
  onChange,
  onRemove,
  onMoveUp,
  onMoveDown,
}: RuleRowProps) {
  function update(patch: Partial<RuleFormState>) {
    onChange({ ...rule, ...patch });
  }

  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[10px] text-dim font-mono w-4 shrink-0 text-center">
        {index + 1}
      </span>

      {/* Field path */}
      <Input
        value={rule.field}
        onChange={(e) => update({ field: e.target.value })}
        placeholder="data.field.path"
        className="bg-surface border-border text-xs h-7 font-mono flex-[3] min-w-0"
      />

      {/* Operator */}
      <Select value={rule.operator} onValueChange={(v) => update({ operator: v as RuleOperator })}>
        <SelectTrigger className="h-7 bg-surface border-border text-xs font-mono w-24 shrink-0" size="sm">
          <SelectValue />
        </SelectTrigger>
        <SelectContent position="popper" className="bg-card border-border">
          {OPERATORS.map((op) => (
            <SelectItem key={op.value} value={op.value} className="text-xs font-mono">
              {op.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* Value */}
      <Input
        value={rule.value}
        onChange={(e) => update({ value: e.target.value })}
        placeholder="threshold"
        className="bg-surface border-border text-xs h-7 font-mono flex-[2] min-w-0"
      />

      {/* Arrow → */}
      <span className="text-[11px] text-dim shrink-0">&rarr;</span>

      {/* Verdict */}
      <Select value={rule.verdict} onValueChange={(v) => update({ verdict: v as MaliceVerdict })}>
        <SelectTrigger className="h-7 bg-surface border-border text-xs w-28 shrink-0" size="sm">
          <SelectValue />
        </SelectTrigger>
        <SelectContent position="popper" className="bg-card border-border">
          {VERDICTS.map((v) => (
            <SelectItem key={v} value={v} className="text-xs">
              {v}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* Actions */}
      <div className="flex items-center gap-0 shrink-0">
        <Button
          variant="ghost"
          size="sm"
          onClick={onMoveUp}
          disabled={index <= 0}
          className="h-6 w-6 p-0 text-dim hover:text-teal"
        >
          <ArrowUp className="h-3 w-3" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onMoveDown}
          disabled={index >= total - 1}
          className="h-6 w-6 p-0 text-dim hover:text-teal"
        >
          <ArrowDown className="h-3 w-3" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onRemove}
          className="h-6 w-6 p-0 text-dim hover:text-red-threat"
        >
          <Trash2 className="h-3 w-3" />
        </Button>
      </div>
    </div>
  );
}
