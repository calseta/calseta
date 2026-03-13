export type TargetingField =
  | "source_name"
  | "severity"
  | "title"
  | "tags"
  | "indicator_type"
  | "indicator_value";

export type TargetingOp =
  | "eq"
  | "in"
  | "contains"
  | "starts_with"
  | "ends_with"
  | "gte"
  | "lte";

export interface TargetingRule {
  field: TargetingField;
  op: TargetingOp;
  value: string | string[] | number;
}

export interface TargetingRules {
  match_any: TargetingRule[];
  match_all: TargetingRule[];
}

interface FieldConfig {
  label: string;
  allowedOps: TargetingOp[];
  valueType: "text" | "select" | "number";
  options?: string[];
}

export const FIELD_CONFIGS: Record<TargetingField, FieldConfig> = {
  source_name: {
    label: "Source",
    allowedOps: ["eq", "in"],
    valueType: "text",
  },
  severity: {
    label: "Severity",
    allowedOps: ["eq", "in"],
    valueType: "select",
    options: ["Pending", "Informational", "Low", "Medium", "High", "Critical"],
  },
  title: {
    label: "Alert Title",
    allowedOps: ["eq", "contains", "starts_with", "ends_with"],
    valueType: "text",
  },
  tags: {
    label: "Tags",
    allowedOps: ["contains"],
    valueType: "text",
  },
  indicator_type: {
    label: "Indicator Type",
    allowedOps: ["eq", "in"],
    valueType: "select",
    options: ["ip", "domain", "hash_md5", "hash_sha1", "hash_sha256", "url", "email", "account"],
  },
  indicator_value: {
    label: "Indicator Value",
    allowedOps: ["eq", "contains", "starts_with", "ends_with"],
    valueType: "text",
  },
};

export const OP_LABELS: Record<TargetingOp, string> = {
  eq: "equals",
  in: "is one of",
  contains: "contains",
  starts_with: "starts with",
  ends_with: "ends with",
  gte: ">=",
  lte: "<=",
};

export const FIELDS = Object.keys(FIELD_CONFIGS) as TargetingField[];

export function serializeTargetingRules(rules: TargetingRules | null): Record<string, unknown> | undefined {
  if (!rules) return undefined;
  const result: Record<string, TargetingRule[]> = {};
  if (rules.match_any.length > 0) result.match_any = rules.match_any;
  if (rules.match_all.length > 0) result.match_all = rules.match_all;
  if (Object.keys(result).length === 0) return undefined;
  return result;
}

export function parseTargetingRules(raw: Record<string, unknown> | null | undefined): TargetingRules | null {
  if (!raw) return null;
  const matchAny = Array.isArray(raw.match_any) ? raw.match_any as TargetingRule[] : [];
  const matchAll = Array.isArray(raw.match_all) ? raw.match_all as TargetingRule[] : [];
  if (matchAny.length === 0 && matchAll.length === 0) return null;
  return { match_any: matchAny, match_all: matchAll };
}
