import { useCallback, useRef } from "react";
import CodeMirror, { type ReactCodeMirrorRef } from "@uiw/react-codemirror";
import { python } from "@codemirror/lang-python";
import { EditorView, keymap } from "@codemirror/view";
import { createTheme } from "@uiw/codemirror-themes";
import { tags as t } from "@lezer/highlight";
import {
  autocompletion,
  type CompletionContext,
  type Completion,
} from "@codemirror/autocomplete";
import { linter, type Diagnostic } from "@codemirror/lint";

/**
 * Calseta dark theme for CodeMirror — matches the app's color palette exactly.
 *
 * Colors pulled from index.css :root variables:
 *   background: #080b0f, surface: #0d1117, surface-hover: #111820
 *   foreground: #CCD0CF, dim: #57635F, border: #1e2a25
 *   teal: #4D7D71, teal-light: #7FCAB8, amber: #FFBB1A, red: #EA591B
 */
const calsetaTheme = createTheme({
  theme: "dark",
  settings: {
    background: "#0d1117",
    foreground: "#CCD0CF",
    caret: "#7FCAB8",
    selection: "#4D7D7133",
    selectionMatch: "#4D7D7122",
    lineHighlight: "#111820",
    gutterBackground: "#0a0d12",
    gutterForeground: "#57635F",
    gutterBorder: "#1e2a25",
    fontFamily: '"IBM Plex Mono", ui-monospace, monospace',
  },
  styles: [
    // Comments
    { tag: t.comment, color: "#57635F", fontStyle: "italic" },
    { tag: t.lineComment, color: "#57635F", fontStyle: "italic" },
    { tag: t.blockComment, color: "#57635F", fontStyle: "italic" },

    // Strings
    { tag: t.string, color: "#7FCAB8" },
    { tag: t.special(t.string), color: "#7FCAB8" },

    // Numbers and booleans
    { tag: t.number, color: "#FFBB1A" },
    { tag: t.bool, color: "#FFBB1A" },

    // Keywords (def, return, if, else, async, await, import, from, etc.)
    { tag: t.keyword, color: "#EA591B" },
    { tag: t.controlKeyword, color: "#EA591B" },

    // Function/method definitions and calls
    { tag: t.function(t.definition(t.variableName)), color: "#7FCAB8", fontWeight: "600" },
    { tag: t.function(t.variableName), color: "#CCD0CF" },

    // Class definitions
    { tag: t.definition(t.className), color: "#FFBB1A", fontWeight: "600" },
    { tag: t.className, color: "#FFBB1A" },

    // Variables and properties
    { tag: t.variableName, color: "#CCD0CF" },
    { tag: t.definition(t.variableName), color: "#CCD0CF" },
    { tag: t.propertyName, color: "#7FCAB8" },

    // Operators and punctuation
    { tag: t.operator, color: "#EA591B" },
    { tag: t.punctuation, color: "#57635F" },
    { tag: t.bracket, color: "#CCD0CF" },

    // Decorators (@)
    { tag: t.meta, color: "#4D7D71" },

    // Type annotations
    { tag: t.typeName, color: "#FFBB1A" },

    // Special: None, self
    { tag: t.null, color: "#FFBB1A" },
    { tag: t.self, color: "#EA591B", fontStyle: "italic" },

    // Built-in names
    { tag: t.standard(t.variableName), color: "#FFBB1A" },
  ],
});

/** Extra editor styles for matching Calseta's visual language. */
const editorBaseTheme = EditorView.theme({
  "&": {
    fontSize: "13px",
    borderRadius: "0.5rem",
    border: "1px solid #1e2a25",
  },
  "&.cm-focused": {
    outline: "1px solid #4D7D71",
    outlineOffset: "-1px",
  },
  ".cm-gutters": {
    borderRight: "1px solid #1e2a25",
    paddingRight: "4px",
  },
  ".cm-activeLineGutter": {
    backgroundColor: "#111820",
    color: "#7FCAB8",
  },
  ".cm-matchingBracket": {
    backgroundColor: "#4D7D7140",
    outline: "1px solid #4D7D7160",
  },
  ".cm-selectionBackground": {
    backgroundColor: "#4D7D7133 !important",
  },
  ".cm-cursor": {
    borderLeftColor: "#7FCAB8",
    borderLeftWidth: "2px",
  },
  ".cm-content": {
    padding: "8px 0",
  },
  ".cm-line": {
    padding: "0 12px",
  },
  // Scrollbar styling
  ".cm-scroller::-webkit-scrollbar": {
    width: "6px",
    height: "6px",
  },
  ".cm-scroller::-webkit-scrollbar-track": {
    background: "transparent",
  },
  ".cm-scroller::-webkit-scrollbar-thumb": {
    background: "#1e2a25",
    borderRadius: "3px",
  },
  ".cm-scroller::-webkit-scrollbar-thumb:hover": {
    background: "#2a3530",
  },
  // Autocomplete tooltip styling
  ".cm-tooltip.cm-tooltip-autocomplete": {
    backgroundColor: "#0d1117",
    border: "1px solid #1e2a25",
    borderRadius: "6px",
    overflow: "hidden",
  },
  ".cm-tooltip.cm-tooltip-autocomplete > ul": {
    fontFamily: '"IBM Plex Mono", ui-monospace, monospace',
    fontSize: "12px",
    maxHeight: "280px",
  },
  ".cm-tooltip.cm-tooltip-autocomplete > ul > li": {
    padding: "4px 8px",
    color: "#CCD0CF",
  },
  ".cm-tooltip.cm-tooltip-autocomplete > ul > li[aria-selected]": {
    backgroundColor: "#4D7D7130",
    color: "#7FCAB8",
  },
  ".cm-completionLabel": {
    color: "#CCD0CF",
  },
  ".cm-completionDetail": {
    color: "#57635F",
    fontStyle: "italic",
    marginLeft: "8px",
  },
  ".cm-completionInfo": {
    backgroundColor: "#0d1117",
    border: "1px solid #1e2a25",
    borderRadius: "6px",
    padding: "8px 12px",
    color: "#CCD0CF",
    fontSize: "12px",
    lineHeight: "1.5",
    maxWidth: "360px",
  },
  // Lint diagnostic styling
  ".cm-diagnostic": {
    padding: "4px 8px",
    fontSize: "12px",
    fontFamily: '"IBM Plex Mono", ui-monospace, monospace',
  },
  ".cm-diagnostic-error": {
    borderLeftColor: "#EA591B",
  },
  ".cm-diagnostic-warning": {
    borderLeftColor: "#FFBB1A",
  },
  ".cm-diagnostic-info": {
    borderLeftColor: "#4D7D71",
  },
  ".cm-tooltip-lint": {
    backgroundColor: "#0d1117",
    border: "1px solid #1e2a25",
    borderRadius: "6px",
  },
  ".cm-lintRange-error": {
    backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='6' height='3'%3E%3Cpath d='M0 3 L1.5 0 L3 3 L4.5 0 L6 3' fill='none' stroke='%23EA591B' stroke-width='0.8'/%3E%3C/svg%3E")`,
  },
  ".cm-lintRange-warning": {
    backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='6' height='3'%3E%3Cpath d='M0 3 L1.5 0 L3 3 L4.5 0 L6 3' fill='none' stroke='%23FFBB1A' stroke-width='0.8'/%3E%3C/svg%3E")`,
  },
  ".cm-lintRange-info": {
    backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='6' height='3'%3E%3Cpath d='M0 3 L1.5 0 L3 3 L4.5 0 L6 3' fill='none' stroke='%234D7D71' stroke-width='0.8'/%3E%3C/svg%3E")`,
  },
});

// ---------------------------------------------------------------------------
// WorkflowContext autocomplete — ctx.* property completions
// ---------------------------------------------------------------------------

interface CtxProperty {
  label: string;
  type: "property" | "method";
  detail: string;
  info: string;
}

/** Top-level ctx.* properties */
const CTX_PROPS: CtxProperty[] = [
  { label: "indicator", type: "property", detail: "IndicatorContext", info: "Read-only indicator data: type, value, malice, enrichment results" },
  { label: "alert", type: "property", detail: "AlertContext | None", info: "Read-only alert data (None for standalone workflows)" },
  { label: "http", type: "property", detail: "httpx.AsyncClient", info: "Async HTTP client — use for GET, POST, PUT, DELETE requests" },
  { label: "log", type: "property", detail: "WorkflowLogger", info: "Structured logger — output captured in workflow run logs" },
  { label: "secrets", type: "property", detail: "SecretsAccessor", info: "Read environment variables via .get(key)" },
  { label: "integrations", type: "property", detail: "IntegrationClients", info: "Pre-built Okta/Entra clients (if configured)" },
];

/** ctx.indicator.* properties */
const CTX_INDICATOR_PROPS: CtxProperty[] = [
  { label: "type", type: "property", detail: "str", info: '"ip", "domain", "hash_sha256", "url", "email", "account", etc.' },
  { label: "value", type: "property", detail: "str", info: 'The indicator value — e.g. "1.2.3.4", "evil.com"' },
  { label: "malice", type: "property", detail: "str", info: '"Pending", "Benign", "Suspicious", or "Malicious"' },
  { label: "uuid", type: "property", detail: "str", info: "Unique identifier for this indicator" },
  { label: "is_enriched", type: "property", detail: "bool", info: "Whether enrichment has been run" },
  { label: "enrichment_results", type: "property", detail: "dict | None", info: "Enrichment data keyed by provider name" },
  { label: "first_seen", type: "property", detail: "datetime", info: "When this indicator was first observed" },
  { label: "last_seen", type: "property", detail: "datetime", info: "When this indicator was last observed" },
  { label: "created_at", type: "property", detail: "datetime", info: "Record creation timestamp" },
  { label: "updated_at", type: "property", detail: "datetime", info: "Record last update timestamp" },
];

/** ctx.alert.* properties */
const CTX_ALERT_PROPS: CtxProperty[] = [
  { label: "uuid", type: "property", detail: "str", info: "Unique identifier for this alert" },
  { label: "title", type: "property", detail: "str", info: "Alert title from the source" },
  { label: "severity", type: "property", detail: "str", info: '"Pending", "Informational", "Low", "Medium", "High", "Critical"' },
  { label: "source_name", type: "property", detail: "str", info: '"sentinel", "elastic", "splunk", etc.' },
  { label: "status", type: "property", detail: "str", info: '"Open", "Triaging", "Escalated", "Closed"' },
  { label: "occurred_at", type: "property", detail: "datetime", info: "When the alert event occurred" },
  { label: "tags", type: "property", detail: "list[str]", info: "Alert tags" },
  { label: "raw_payload", type: "property", detail: "dict", info: "Original source payload (all fields preserved)" },
];

/** ctx.http.* methods */
const CTX_HTTP_PROPS: CtxProperty[] = [
  { label: "get", type: "method", detail: "(url, **kwargs) -> Response", info: "await ctx.http.get(url, headers={...}, params={...})" },
  { label: "post", type: "method", detail: "(url, **kwargs) -> Response", info: "await ctx.http.post(url, json={...}, headers={...})" },
  { label: "put", type: "method", detail: "(url, **kwargs) -> Response", info: "await ctx.http.put(url, json={...}, headers={...})" },
  { label: "patch", type: "method", detail: "(url, **kwargs) -> Response", info: "await ctx.http.patch(url, json={...}, headers={...})" },
  { label: "delete", type: "method", detail: "(url, **kwargs) -> Response", info: "await ctx.http.delete(url, headers={...})" },
];

/** ctx.log.* methods */
const CTX_LOG_PROPS: CtxProperty[] = [
  { label: "info", type: "method", detail: "(message, **kwargs)", info: 'ctx.log.info("step_completed", key="value")' },
  { label: "warning", type: "method", detail: "(message, **kwargs)", info: 'ctx.log.warning("rate_limited", retry_after=60)' },
  { label: "error", type: "method", detail: "(message, **kwargs)", info: 'ctx.log.error("api_failed", status=resp.status_code)' },
  { label: "debug", type: "method", detail: "(message, **kwargs)", info: 'ctx.log.debug("payload", data=payload)' },
];

/** ctx.secrets.* methods */
const CTX_SECRETS_PROPS: CtxProperty[] = [
  { label: "get", type: "method", detail: "(key: str) -> str | None", info: 'Read an environment variable: ctx.secrets.get("API_TOKEN")' },
];

/** ctx.integrations.* properties */
const CTX_INTEGRATIONS_PROPS: CtxProperty[] = [
  { label: "okta", type: "property", detail: "OktaClient | None", info: "Pre-authenticated Okta client (requires OKTA_DOMAIN + OKTA_API_TOKEN)" },
  { label: "entra", type: "property", detail: "EntraClient | None", info: "Pre-authenticated Entra client (requires ENTRA_TENANT_ID + ENTRA_CLIENT_ID + ENTRA_CLIENT_SECRET)" },
];

/** httpx Response properties (for resp.* completions) */
const RESP_PROPS: CtxProperty[] = [
  { label: "status_code", type: "property", detail: "int", info: "HTTP status code (200, 404, 500, etc.)" },
  { label: "text", type: "property", detail: "str", info: "Response body as a string" },
  { label: "json", type: "method", detail: "() -> dict", info: "Parse response body as JSON: data = resp.json()" },
  { label: "headers", type: "property", detail: "Headers", info: "Response headers (dict-like)" },
  { label: "is_success", type: "property", detail: "bool", info: "True if status_code is 2xx" },
  { label: "is_error", type: "property", detail: "bool", info: "True if status_code is 4xx or 5xx" },
  { label: "url", type: "property", detail: "URL", info: "The final URL (after redirects)" },
  { label: "content", type: "property", detail: "bytes", info: "Response body as raw bytes" },
];

/** WorkflowResult static methods */
const WORKFLOW_RESULT_PROPS: CtxProperty[] = [
  { label: "ok", type: "method", detail: '(message, data={}) -> WorkflowResult', info: 'WorkflowResult.ok("Success", data={"key": "value"})' },
  { label: "fail", type: "method", detail: '(message, data={}) -> WorkflowResult', info: 'WorkflowResult.fail("API returned error", data={"status": 500})' },
];

/** Map dotted prefix → completions list */
const COMPLETION_MAP: Record<string, CtxProperty[]> = {
  "ctx.": CTX_PROPS,
  "ctx.indicator.": CTX_INDICATOR_PROPS,
  "ctx.alert.": CTX_ALERT_PROPS,
  "ctx.http.": CTX_HTTP_PROPS,
  "ctx.log.": CTX_LOG_PROPS,
  "ctx.secrets.": CTX_SECRETS_PROPS,
  "ctx.integrations.": CTX_INTEGRATIONS_PROPS,
  "WorkflowResult.": WORKFLOW_RESULT_PROPS,
};

/** Variable names that likely hold an httpx Response */
const RESP_VAR_PATTERN = /\b(resp|response|res|r)\.\s*$/;

function toCompletions(items: CtxProperty[]): Completion[] {
  return items.map((p) => ({
    label: p.label,
    type: p.type,
    detail: p.detail,
    info: p.info,
    boost: p.type === "property" ? 1 : 0,
  }));
}

function workflowCompletionSource(context: CompletionContext) {
  // Get text from line start to cursor
  const line = context.state.doc.lineAt(context.pos);
  const textBefore = line.text.slice(0, context.pos - line.from);

  // Check each known prefix (longest first to match most specific)
  const sortedPrefixes = Object.keys(COMPLETION_MAP).sort(
    (a, b) => b.length - a.length,
  );

  for (const prefix of sortedPrefixes) {
    if (textBefore.endsWith(prefix)) {
      return {
        from: context.pos,
        options: toCompletions(COMPLETION_MAP[prefix]),
        validFor: /^\w*$/,
      };
    }
    // Also match when user has started typing after the dot (e.g. "ctx.ind")
    const dotIdx = prefix.length - 1; // position of trailing dot
    const base = prefix.slice(0, dotIdx + 1); // e.g. "ctx."
    const match = textBefore.match(
      new RegExp(escapeRegex(base) + "(\\w+)$"),
    );
    if (match && prefix === base) {
      return {
        from: context.pos - match[1].length,
        options: toCompletions(COMPLETION_MAP[prefix]),
        validFor: /^\w*$/,
      };
    }
  }

  // Check for resp.* pattern (httpx Response)
  if (RESP_VAR_PATTERN.test(textBefore)) {
    return {
      from: context.pos,
      options: toCompletions(RESP_PROPS),
      validFor: /^\w*$/,
    };
  }
  // Also match partial typing after resp. (e.g. "resp.sta")
  const respMatch = textBefore.match(/\b(resp|response|res|r)\.(\w+)$/);
  if (respMatch) {
    return {
      from: context.pos - respMatch[2].length,
      options: toCompletions(RESP_PROPS),
      validFor: /^\w*$/,
    };
  }

  return null;
}

function escapeRegex(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

const workflowAutocompletion = autocompletion({
  override: [workflowCompletionSource],
  activateOnTyping: true,
  icons: false,
});

// ---------------------------------------------------------------------------
// Workflow linter — catches common mistakes before you hit "Test"
// ---------------------------------------------------------------------------

/** Modules blocked by the backend AST validator */
const BLOCKED_MODULES = new Set([
  "os", "subprocess", "importlib", "sys", "builtins", "socket", "ctypes",
  "pickle", "shelve", "shutil", "tempfile", "pty", "termios", "resource",
  "signal", "multiprocessing", "concurrent", "threading", "gc", "weakref",
  "code", "codeop", "compileall", "dis", "tokenize", "token",
]);

/** Blocked built-in function calls */
const BLOCKED_BUILTINS = new Set([
  "exec", "eval", "compile", "__import__", "open", "breakpoint", "input", "memoryview",
]);

/** Valid ctx.* top-level attributes */
const VALID_CTX_ATTRS = new Set([
  "indicator", "alert", "http", "log", "secrets", "integrations",
]);

/** Known invalid response attributes that people try to use */
const INVALID_RESP_ATTRS: Record<string, string> = {
  body: "Use .text (string) or .json() (dict) instead",
  data: "Use .json() to parse the response body",
  status: "Use .status_code instead",
  ok: "Use .is_success instead",
};

interface LintRule {
  /** Regex to match against each line (non-comment) */
  pattern: RegExp;
  /** Severity of the diagnostic */
  severity: "error" | "warning" | "info";
  /** Message to display */
  message: string | ((match: RegExpExecArray) => string);
  /** Optional: override which part of the match to underline (default: full match) */
  group?: number;
}

const LINE_RULES: LintRule[] = [
  // --- Blocked imports ---
  {
    pattern: /\bimport\s+(os|subprocess|importlib|sys|socket|ctypes|pickle|shelve|shutil|tempfile|multiprocessing|threading)\b/,
    severity: "error",
    message: (m) => `Import of '${m[1]}' is blocked — not allowed in workflows`,
  },
  {
    pattern: /\bfrom\s+(os|subprocess|importlib|sys|socket|ctypes|pickle|shelve|shutil|tempfile|multiprocessing|threading)\b/,
    severity: "error",
    message: (m) => `Import from '${m[1]}' is blocked — not allowed in workflows`,
  },

  // --- Blocked builtins ---
  {
    pattern: /\b(exec|eval|compile|__import__|breakpoint|memoryview)\s*\(/,
    severity: "error",
    message: (m) => `'${m[1]}()' is blocked in workflows`,
    group: 1,
  },
  {
    pattern: /\bopen\s*\(/,
    severity: "error",
    message: "File I/O is blocked — use ctx.http for external calls",
  },

  // --- Wrong ctx attributes ---
  {
    pattern: /\bctx\.result\b/,
    severity: "error",
    message: "ctx has no attribute 'result' — use WorkflowResult.ok() or WorkflowResult.fail()",
  },
  {
    pattern: /\bctx\.response\b/,
    severity: "error",
    message: "ctx has no attribute 'response' — use ctx.http.get/post() to make HTTP calls",
  },
  {
    pattern: /\bctx\.config\b/,
    severity: "error",
    message: "ctx has no attribute 'config' — use ctx.secrets.get(\"KEY\") for env vars",
  },
  {
    pattern: /\bctx\.env\b/,
    severity: "error",
    message: "ctx has no attribute 'env' — use ctx.secrets.get(\"KEY\") for env vars",
  },

  // --- Wrong response attributes ---
  {
    pattern: /\b(?:resp|response|res)\.(body)\b/,
    severity: "error",
    message: "Response has no attribute 'body' — use .text (string) or .json() (dict)",
    group: 0,
  },
  {
    pattern: /\b(?:resp|response|res)\.(data)\b(?!\s*=)/,
    severity: "warning",
    message: "Response has no attribute 'data' — use .json() to parse the response body",
    group: 0,
  },
  {
    pattern: /\b(?:resp|response|res)\.status\b(?!_code)/,
    severity: "warning",
    message: "Did you mean .status_code? httpx Response uses status_code, not status",
    group: 0,
  },

  // --- Missing await on async calls ---
  {
    pattern: /(?<!await\s)(?<!await\s{2})(?<!await\s{3})\bctx\.http\.(get|post|put|patch|delete)\s*\(/,
    severity: "warning",
    message: (m) => `ctx.http.${m[1]}() is async — did you forget 'await'?`,
  },

  // --- raise inside workflow ---
  {
    pattern: /^\s*raise\s+\w+/,
    severity: "warning",
    message: "Workflows should never raise — return WorkflowResult.fail() instead",
  },

  // --- WorkflowResult misuse ---
  {
    pattern: /\bWorkflowResult\.success\b/,
    severity: "error",
    message: "WorkflowResult has no method 'success' — use WorkflowResult.ok()",
  },
  {
    pattern: /\bWorkflowResult\.error\b/,
    severity: "error",
    message: "WorkflowResult has no method 'error' — use WorkflowResult.fail()",
  },
  {
    pattern: /\bWorkflowResult\(\s*success\s*=/,
    severity: "info",
    message: "Prefer WorkflowResult.ok() or WorkflowResult.fail() over direct construction",
  },

  // --- print() ---
  {
    pattern: /\bprint\s*\(/,
    severity: "warning",
    message: "Use ctx.log.info() instead of print() — print output is not captured",
  },
];

/** Check if a line is inside a comment or string (simple heuristic) */
function isCommentLine(line: string): boolean {
  const trimmed = line.trimStart();
  return trimmed.startsWith("#");
}

function workflowLintSource(view: EditorView): Diagnostic[] {
  const doc = view.state.doc;
  const text = doc.toString();
  const diagnostics: Diagnostic[] = [];

  // --- Document-level checks ---

  // Must have async def run
  const hasAsyncDefRun = /^async\s+def\s+run\s*\(/m.test(text);
  const hasSyncDefRun = /^def\s+run\s*\(/m.test(text);

  if (!hasAsyncDefRun && hasSyncDefRun) {
    // Find the sync def run and underline it
    const match = /^def\s+run\s*\(/m.exec(text);
    if (match) {
      diagnostics.push({
        from: match.index,
        to: match.index + match[0].length - 1,
        severity: "error",
        message: "run() must be async — change to 'async def run(ctx)'",
      });
    }
  } else if (!hasAsyncDefRun && !hasSyncDefRun) {
    // No run function at all — mark at the top
    diagnostics.push({
      from: 0,
      to: Math.min(doc.line(1).to, doc.length),
      severity: "error",
      message: "Workflow must define 'async def run(ctx)' — this is the entry point",
    });
  }

  // --- Per-line checks ---
  for (let i = 1; i <= doc.lines; i++) {
    const line = doc.line(i);
    const lineText = line.text;

    // Skip comment lines
    if (isCommentLine(lineText)) continue;

    // Skip lines that are inside triple-quoted strings (simple heuristic)
    // We just skip lines that don't have any code-like content
    if (lineText.trim() === "") continue;

    for (const rule of LINE_RULES) {
      // Reset lastIndex for global-like behavior
      const regex = new RegExp(rule.pattern.source, rule.pattern.flags);
      let match: RegExpExecArray | null;

      while ((match = regex.exec(lineText)) !== null) {
        // Calculate the character range to underline
        const matchStart = line.from + match.index;
        const matchLen = rule.group !== undefined && match[rule.group]
          ? match[rule.group].length
          : match[0].length;
        const matchFrom = rule.group !== undefined && match[rule.group]
          ? line.from + lineText.indexOf(match[rule.group], match.index)
          : matchStart;

        diagnostics.push({
          from: matchFrom,
          to: matchFrom + matchLen,
          severity: rule.severity,
          message: typeof rule.message === "function"
            ? rule.message(match)
            : rule.message,
        });

        // Avoid infinite loop on zero-length matches
        if (!regex.global) break;
      }
    }
  }

  return diagnostics;
}

const workflowLinter = linter(workflowLintSource, { delay: 400 });

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface WorkflowCodeEditorProps {
  value: string;
  onChange: (value: string) => void;
  onSave?: () => void;
  height?: string;
  readOnly?: boolean;
}

export function WorkflowCodeEditor({
  value,
  onChange,
  onSave,
  height = "500px",
  readOnly = false,
}: WorkflowCodeEditorProps) {
  const editorRef = useRef<ReactCodeMirrorRef>(null);

  const saveKeymap = useCallback(() => {
    if (!onSave) return [];
    return [
      keymap.of([
        {
          key: "Mod-s",
          run: () => {
            onSave();
            return true;
          },
        },
      ]),
    ];
  }, [onSave]);

  return (
    <CodeMirror
      ref={editorRef}
      value={value}
      onChange={onChange}
      height={height}
      theme={calsetaTheme}
      readOnly={readOnly}
      basicSetup={{
        lineNumbers: true,
        highlightActiveLineGutter: true,
        highlightActiveLine: true,
        bracketMatching: true,
        closeBrackets: true,
        autocompletion: false, // disabled — using our custom one below
        indentOnInput: true,
        foldGutter: true,
        tabSize: 4,
      }}
      extensions={[
        python(),
        editorBaseTheme,
        workflowAutocompletion,
        workflowLinter,
        ...saveKeymap(),
      ]}
    />
  );
}
