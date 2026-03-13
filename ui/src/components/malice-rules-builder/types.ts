// --- Domain types (match backend JSON exactly) ---

export type MaliceVerdict = "Pending" | "Benign" | "Suspicious" | "Malicious";

export type RuleOperator = ">" | ">=" | "<" | "<=" | "==" | "!=" | "contains" | "in";

export interface MaliceRule {
  field: string;
  operator: RuleOperator;
  value: unknown;
  verdict: MaliceVerdict;
}

export interface MaliceRules {
  rules: MaliceRule[];
  default_verdict: MaliceVerdict;
  not_found_verdict: MaliceVerdict;
}

// --- Form state types ---

export interface RuleFormState {
  id: string;
  field: string;
  operator: RuleOperator;
  value: string;
  verdict: MaliceVerdict;
}

// --- Constants ---

export const VERDICTS: MaliceVerdict[] = ["Pending", "Benign", "Suspicious", "Malicious"];

export const OPERATORS: { value: RuleOperator; label: string }[] = [
  { value: ">", label: ">" },
  { value: ">=", label: ">=" },
  { value: "<", label: "<" },
  { value: "<=", label: "<=" },
  { value: "==", label: "==" },
  { value: "!=", label: "!=" },
  { value: "contains", label: "contains" },
  { value: "in", label: "in" },
];

export const VERDICT_COLORS: Record<MaliceVerdict, string> = {
  Malicious: "bg-red-threat/15 text-red-threat border-red-threat/30",
  Suspicious: "bg-amber/15 text-amber border-amber/30",
  Benign: "bg-teal/15 text-teal border-teal/30",
  Pending: "bg-muted/50 text-dim border-border",
};

// --- Conversion functions ---

let nextId = 0;
function genId(): string {
  return `mr-${++nextId}`;
}

function serializeValue(raw: string, operator: RuleOperator): unknown {
  const trimmed = raw.trim();

  // "in" operator expects an array
  if (operator === "in") {
    try {
      const parsed = JSON.parse(trimmed);
      if (Array.isArray(parsed)) return parsed;
    } catch {
      // Fall through — treat as comma-separated
    }
    return trimmed.split(",").map((s) => s.trim());
  }

  // Try numeric
  const num = Number(trimmed);
  if (trimmed !== "" && !isNaN(num)) return num;

  // Try boolean
  if (trimmed === "true") return true;
  if (trimmed === "false") return false;

  return trimmed;
}

function deserializeValue(val: unknown): string {
  if (val === null || val === undefined) return "";
  if (Array.isArray(val)) return JSON.stringify(val);
  return String(val);
}

export function maliceRulesToFormState(rules: MaliceRules): {
  ruleRows: RuleFormState[];
  defaultVerdict: MaliceVerdict;
  notFoundVerdict: MaliceVerdict;
} {
  return {
    ruleRows: rules.rules.map((r) => ({
      id: genId(),
      field: r.field,
      operator: r.operator,
      value: deserializeValue(r.value),
      verdict: r.verdict,
    })),
    defaultVerdict: rules.default_verdict,
    notFoundVerdict: rules.not_found_verdict,
  };
}

export function formStateToMaliceRules(
  ruleRows: RuleFormState[],
  defaultVerdict: MaliceVerdict,
  notFoundVerdict: MaliceVerdict,
): MaliceRules {
  return {
    rules: ruleRows
      .filter((r) => r.field.trim() !== "")
      .map((r) => ({
        field: r.field,
        operator: r.operator,
        value: serializeValue(r.value, r.operator),
        verdict: r.verdict,
      })),
    default_verdict: defaultVerdict,
    not_found_verdict: notFoundVerdict,
  };
}

export function parseMaliceRules(
  raw: Record<string, unknown> | null | undefined,
): MaliceRules | null {
  if (!raw) return null;
  return {
    rules: Array.isArray(raw.rules) ? (raw.rules as MaliceRule[]) : [],
    default_verdict: (raw.default_verdict as MaliceVerdict) ?? "Pending",
    not_found_verdict: (raw.not_found_verdict as MaliceVerdict) ?? "Pending",
  };
}

export function createEmptyRule(): RuleFormState {
  return {
    id: genId(),
    field: "",
    operator: ">=",
    value: "",
    verdict: "Malicious",
  };
}
