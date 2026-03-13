// --- Domain types (match backend JSON exactly) ---

export type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface HttpStep {
  name: string;
  method: HttpMethod;
  url: string;
  headers?: Record<string, string>;
  query_params?: Record<string, string>;
  json_body?: Record<string, unknown>;
  form_body?: Record<string, string>;
  timeout_seconds?: number;
  expected_status?: number[];
  not_found_status?: number[];
  optional?: boolean;
}

export interface HttpConfig {
  steps: HttpStep[];
  url_templates_by_type?: Record<string, string>;
}

// --- Form state types (React-friendly with stable IDs) ---

export interface KeyValueRow {
  id: string;
  key: string;
  value: string;
}

export type BodyMode = "none" | "json_body" | "form_body";

export interface StepFormState {
  id: string;
  name: string;
  method: HttpMethod;
  url: string;
  headers: KeyValueRow[];
  queryParams: KeyValueRow[];
  bodyMode: BodyMode;
  jsonBody: string;
  formBody: KeyValueRow[];
  timeoutSeconds: string;
  expectedStatus: string;
  notFoundStatus: string;
  optional: boolean;
  collapsed: boolean;
}

export interface UrlTemplateRow {
  id: string;
  indicatorType: string;
  urlTemplate: string;
}

// --- Constants ---

export const HTTP_METHODS: HttpMethod[] = ["GET", "POST", "PUT", "PATCH", "DELETE"];

export const INDICATOR_TYPES = [
  "ip",
  "domain",
  "hash_md5",
  "hash_sha1",
  "hash_sha256",
  "url",
  "email",
  "account",
] as const;

export const TEMPLATE_VARIABLES: { variable: string; description: string }[] = [
  { variable: "{{indicator.value}}", description: "The indicator value being enriched" },
  { variable: "{{indicator.type}}", description: "The indicator type (ip, domain, hash_md5, etc.)" },
  { variable: "{{prev.status}}", description: "HTTP status code from the previous step" },
  { variable: "{{prev.body}}", description: "Parsed JSON body from the previous step" },
  { variable: "{{prev.headers}}", description: "Response headers from the previous step" },
];

export const METHOD_COLORS: Record<HttpMethod, string> = {
  GET: "bg-teal/15 text-teal border-teal/30",
  POST: "bg-amber/15 text-amber border-amber/30",
  PUT: "bg-teal-light/15 text-teal-light border-teal-light/30",
  PATCH: "bg-teal-light/15 text-teal-light border-teal-light/30",
  DELETE: "bg-red-threat/15 text-red-threat border-red-threat/30",
};

// --- Conversion functions ---

let nextId = 0;
function genId(): string {
  return `hcb-${++nextId}`;
}

function kvRowsFromRecord(rec: Record<string, string> | undefined): KeyValueRow[] {
  if (!rec || Object.keys(rec).length === 0) return [];
  return Object.entries(rec).map(([key, value]) => ({ id: genId(), key, value }));
}

function kvRowsToRecord(rows: KeyValueRow[]): Record<string, string> | undefined {
  const filtered = rows.filter((r) => r.key.trim() !== "");
  if (filtered.length === 0) return undefined;
  const rec: Record<string, string> = {};
  for (const r of filtered) rec[r.key] = r.value;
  return rec;
}

function determineBodyMode(step: HttpStep): BodyMode {
  if (step.json_body && Object.keys(step.json_body).length > 0) return "json_body";
  if (step.form_body && Object.keys(step.form_body).length > 0) return "form_body";
  return "none";
}

function numberArrayToString(arr: number[] | undefined): string {
  if (!arr || arr.length === 0) return "";
  return arr.join(", ");
}

function stringToNumberArray(s: string): number[] | undefined {
  const trimmed = s.trim();
  if (!trimmed) return undefined;
  const nums = trimmed
    .split(/[,\s]+/)
    .map((v) => parseInt(v, 10))
    .filter((n) => !isNaN(n));
  return nums.length > 0 ? nums : undefined;
}

export function httpConfigToFormState(config: HttpConfig): {
  steps: StepFormState[];
  urlTemplates: UrlTemplateRow[];
} {
  const steps: StepFormState[] = (config.steps || []).map((step) => ({
    id: genId(),
    name: step.name || "",
    method: step.method || "GET",
    url: step.url || "",
    headers: kvRowsFromRecord(step.headers),
    queryParams: kvRowsFromRecord(step.query_params),
    bodyMode: determineBodyMode(step),
    jsonBody: step.json_body ? JSON.stringify(step.json_body, null, 2) : "",
    formBody: kvRowsFromRecord(step.form_body),
    timeoutSeconds: step.timeout_seconds != null ? String(step.timeout_seconds) : "",
    expectedStatus: numberArrayToString(step.expected_status),
    notFoundStatus: numberArrayToString(step.not_found_status),
    optional: step.optional ?? false,
    collapsed: true,
  }));

  const urlTemplates: UrlTemplateRow[] = config.url_templates_by_type
    ? Object.entries(config.url_templates_by_type).map(([indicatorType, urlTemplate]) => ({
        id: genId(),
        indicatorType,
        urlTemplate,
      }))
    : [];

  return { steps, urlTemplates };
}

export function formStateToHttpConfig(
  steps: StepFormState[],
  urlTemplates: UrlTemplateRow[],
): HttpConfig {
  const httpSteps: HttpStep[] = steps.map((s) => {
    const step: HttpStep = {
      name: s.name,
      method: s.method,
      url: s.url,
    };

    const headers = kvRowsToRecord(s.headers);
    if (headers) step.headers = headers;

    const queryParams = kvRowsToRecord(s.queryParams);
    if (queryParams) step.query_params = queryParams;

    if (s.bodyMode === "json_body" && s.jsonBody.trim()) {
      try {
        step.json_body = JSON.parse(s.jsonBody);
      } catch {
        // Keep raw string in a wrapper so it round-trips
        step.json_body = { _raw: s.jsonBody };
      }
    } else if (s.bodyMode === "form_body") {
      const formBody = kvRowsToRecord(s.formBody);
      if (formBody) step.form_body = formBody;
    }

    const timeout = parseInt(s.timeoutSeconds, 10);
    if (!isNaN(timeout) && timeout > 0) step.timeout_seconds = timeout;

    const expected = stringToNumberArray(s.expectedStatus);
    if (expected) step.expected_status = expected;

    const notFound = stringToNumberArray(s.notFoundStatus);
    if (notFound) step.not_found_status = notFound;

    if (s.optional) step.optional = true;

    return step;
  });

  const config: HttpConfig = { steps: httpSteps };

  const filteredTemplates = urlTemplates.filter(
    (t) => t.indicatorType.trim() && t.urlTemplate.trim(),
  );
  if (filteredTemplates.length > 0) {
    config.url_templates_by_type = {};
    for (const t of filteredTemplates) {
      config.url_templates_by_type[t.indicatorType] = t.urlTemplate;
    }
  }

  return config;
}

export function parseHttpConfig(raw: Record<string, unknown> | null | undefined): HttpConfig | null {
  if (!raw) return null;
  const steps = Array.isArray(raw.steps) ? (raw.steps as HttpStep[]) : [];
  const urlTemplatesByType =
    raw.url_templates_by_type && typeof raw.url_templates_by_type === "object"
      ? (raw.url_templates_by_type as Record<string, string>)
      : undefined;
  return { steps, url_templates_by_type: urlTemplatesByType };
}

export function createEmptyStep(): StepFormState {
  return {
    id: genId(),
    name: "",
    method: "GET",
    url: "",
    headers: [],
    queryParams: [],
    bodyMode: "none",
    jsonBody: "",
    formBody: [],
    timeoutSeconds: "",
    expectedStatus: "",
    notFoundStatus: "",
    optional: false,
    collapsed: false,
  };
}

export function createEmptyKvRow(): KeyValueRow {
  return { id: genId(), key: "", value: "" };
}

export function createEmptyUrlTemplate(): UrlTemplateRow {
  return { id: genId(), indicatorType: "", urlTemplate: "" };
}
