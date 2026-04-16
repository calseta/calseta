import { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { Code2, Plus } from "lucide-react";
import { RuleRow } from "./rule-row";
import type { MaliceRules, MaliceVerdict, RuleFormState } from "./types";
import {
  VERDICTS,
  maliceRulesToFormState,
  formStateToMaliceRules,
  createEmptyRule,
} from "./types";

interface MaliceRulesBuilderProps {
  value: MaliceRules;
  onChange: (rules: MaliceRules) => void;
}

export function MaliceRulesBuilder({ value, onChange }: MaliceRulesBuilderProps) {
  const [ruleRows, setRuleRows] = useState<RuleFormState[]>([]);
  const [defaultVerdict, setDefaultVerdict] = useState<MaliceVerdict>("Pending");
  const [notFoundVerdict, setNotFoundVerdict] = useState<MaliceVerdict>("Pending");
  const [rawJsonMode, setRawJsonMode] = useState(false);
  const [rawJsonText, setRawJsonText] = useState("");
  const [rawJsonError, setRawJsonError] = useState<string | null>(null);
  const initialized = useRef(false);

  useEffect(() => {
    if (!initialized.current) {
      const state = maliceRulesToFormState(value);
      setRuleRows(state.ruleRows);
      setDefaultVerdict(state.defaultVerdict);
      setNotFoundVerdict(state.notFoundVerdict);
      initialized.current = true;
    }
  }, [value]);

  function emitChange(
    rows: RuleFormState[],
    defVerdict: MaliceVerdict,
    nfVerdict: MaliceVerdict,
  ) {
    onChange(formStateToMaliceRules(rows, defVerdict, nfVerdict));
  }

  function updateRuleRows(rows: RuleFormState[]) {
    setRuleRows(rows);
    emitChange(rows, defaultVerdict, notFoundVerdict);
  }

  function handleDefaultVerdictChange(v: MaliceVerdict) {
    setDefaultVerdict(v);
    emitChange(ruleRows, v, notFoundVerdict);
  }

  function handleNotFoundVerdictChange(v: MaliceVerdict) {
    setNotFoundVerdict(v);
    emitChange(ruleRows, defaultVerdict, v);
  }

  function addRule() {
    updateRuleRows([...ruleRows, createEmptyRule()]);
  }

  function removeRule(id: string) {
    updateRuleRows(ruleRows.filter((r) => r.id !== id));
  }

  function updateRule(id: string, updated: RuleFormState) {
    updateRuleRows(ruleRows.map((r) => (r.id === id ? updated : r)));
  }

  function moveRule(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= ruleRows.length) return;
    const newRows = [...ruleRows];
    [newRows[index], newRows[target]] = [newRows[target], newRows[index]];
    updateRuleRows(newRows);
  }

  // --- Raw JSON toggle ---
  function enterRawMode() {
    const config = formStateToMaliceRules(ruleRows, defaultVerdict, notFoundVerdict);
    setRawJsonText(JSON.stringify(config, null, 2));
    setRawJsonError(null);
    setRawJsonMode(true);
  }

  function exitRawMode() {
    try {
      const parsed = JSON.parse(rawJsonText);
      const config: MaliceRules = {
        rules: Array.isArray(parsed.rules) ? parsed.rules : [],
        default_verdict: parsed.default_verdict ?? "Pending",
        not_found_verdict: parsed.not_found_verdict ?? "Pending",
      };
      const state = maliceRulesToFormState(config);
      setRuleRows(state.ruleRows);
      setDefaultVerdict(state.defaultVerdict);
      setNotFoundVerdict(state.notFoundVerdict);
      setRawJsonError(null);
      setRawJsonMode(false);
      onChange(config);
    } catch (e) {
      setRawJsonError(e instanceof Error ? e.message : "Invalid JSON");
    }
  }

  if (rawJsonMode) {
    return (
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-[11px] text-dim font-medium">Raw JSON</p>
          <Button
            variant="outline"
            size="sm"
            onClick={exitRawMode}
            className="h-7 text-xs text-dim hover:text-teal"
          >
            <Code2 className="h-3 w-3 mr-1" />
            Visual Editor
          </Button>
        </div>
        <Textarea
          value={rawJsonText}
          onChange={(e) => {
            setRawJsonText(e.target.value);
            setRawJsonError(null);
          }}
          rows={12}
          className="bg-surface border-border text-sm font-mono"
        />
        {rawJsonError && (
          <p className="text-[11px] text-red-threat">{rawJsonError}</p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <p className="text-[11px] text-dim font-medium">
          Threshold Rules
          <span className="text-dim/60 ml-1">(first match wins)</span>
        </p>
        <Button
          variant="outline"
          size="sm"
          onClick={enterRawMode}
          className="h-7 text-xs text-dim hover:text-teal"
        >
          <Code2 className="h-3 w-3 mr-1" />
          Raw JSON
        </Button>
      </div>

      {/* Rules */}
      {ruleRows.length > 0 && (
        <div className="space-y-1.5 surface-2 rounded-md p-2">
          {ruleRows.map((rule, i) => (
            <RuleRow
              key={rule.id}
              rule={rule}
              index={i}
              total={ruleRows.length}
              onChange={(updated) => updateRule(rule.id, updated)}
              onRemove={() => removeRule(rule.id)}
              onMoveUp={() => moveRule(i, -1)}
              onMoveDown={() => moveRule(i, 1)}
            />
          ))}
        </div>
      )}

      <Button
        variant="outline"
        size="sm"
        onClick={addRule}
        className={cn(
          "text-xs border-dashed border-border text-dim hover:text-teal hover:border-teal/40 w-full",
          ruleRows.length === 0 && "py-3",
        )}
      >
        <Plus className="h-3 w-3 mr-1" />
        Add Rule
      </Button>

      {/* Verdicts */}
      <Separator className="my-1" />
      <div className="flex gap-4">
        <VerdictSelect
          label="Default Verdict"
          description="When no rule matches"
          value={defaultVerdict}
          onChange={handleDefaultVerdictChange}
        />
        <VerdictSelect
          label="Not Found Verdict"
          description="When provider returns 404"
          value={notFoundVerdict}
          onChange={handleNotFoundVerdictChange}
        />
      </div>
    </div>
  );
}

function VerdictSelect({
  label,
  description,
  value,
  onChange,
}: {
  label: string;
  description: string;
  value: MaliceVerdict;
  onChange: (v: MaliceVerdict) => void;
}) {
  return (
    <div className="flex-1">
      <p className="text-[11px] text-dim font-medium">{label}</p>
      <p className="text-[10px] text-dim/60 mb-1">{description}</p>
      <Select value={value} onValueChange={(v) => onChange(v as MaliceVerdict)}>
        <SelectTrigger className="h-7 bg-surface border-border text-xs" size="sm">
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
    </div>
  );
}
