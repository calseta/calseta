// API response envelopes
export interface DataResponse<T> {
  data: T;
  meta: Record<string, unknown>;
}

export interface PaginatedResponse<T> {
  data: T[];
  meta: {
    total: number;
    page: number;
    page_size: number;
    total_pages: number;
  };
}

// Alerts
export type AlertStatus =
  | "pending_enrichment"
  | "enriched"
  | "Open"
  | "Triaging"
  | "Escalated"
  | "Closed";

export type AlertSeverity =
  | "Pending"
  | "Informational"
  | "Low"
  | "Medium"
  | "High"
  | "Critical";

export type AlertCloseClassification =
  | "True Positive - Suspicious Activity"
  | "Benign Positive - Suspicious but Expected"
  | "False Positive - Incorrect Detection Logic"
  | "False Positive - Inaccurate Data"
  | "Undetermined"
  | "Duplicate"
  | "Not Applicable";

export interface AlertSummary {
  uuid: string;
  title: string;
  severity: AlertSeverity;
  severity_id: number;
  status: AlertStatus;
  source_name: string;
  occurred_at: string;
  ingested_at: string;
  is_enriched: boolean;
  tags: string[];
  created_at: string;
}

export interface AlertResponse extends AlertSummary {
  enriched_at: string | null;
  fingerprint: string | null;
  close_classification: AlertCloseClassification | null;
  acknowledged_at: string | null;
  triaged_at: string | null;
  closed_at: string | null;
  detection_rule_id: number | null;
  indicators: EnrichedIndicator[];
  agent_findings: AgentFinding[] | null;
  raw_payload: Record<string, unknown> | null;
  updated_at: string;
}

export interface EnrichedIndicator {
  uuid: string;
  type: string;
  value: string;
  first_seen: string;
  last_seen: string;
  is_enriched: boolean;
  malice: string;
  enrichment_results: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface AgentFinding {
  id: string;
  agent_name: string;
  summary: string;
  confidence: string | null;
  recommended_action: string | null;
  evidence: Record<string, unknown> | null;
  posted_at: string;
}

// Activity Events
export interface ActivityEvent {
  uuid: string;
  event_type: string;
  actor_type: string;
  actor_key_prefix: string | null;
  references: Record<string, unknown> | null;
  created_at: string;
}

// Context Documents (list endpoint returns summary — no content field)
export interface ContextDocument {
  uuid: string;
  title: string;
  document_type: string;
  is_global: boolean;
  description: string | null;
  content?: string;
  targeting_rules?: Record<string, unknown> | null;
  tags: string[];
  version: number;
  created_at: string;
  updated_at: string;
}

// Metrics
export interface MetricsSummary {
  period: string;
  alerts: {
    total: number;
    active: number;
    by_severity: Record<string, number>;
    false_positive_rate: number;
    mttd_seconds: number | null;
    mtta_seconds: number | null;
    mttt_seconds: number | null;
    mttc_seconds: number | null;
  };
  workflows: {
    total_configured: number;
    executions: number;
    success_rate: number;
    estimated_time_saved_hours: number;
  };
  approvals: {
    pending: number;
    approved_last_30_days: number;
    approval_rate: number;
    median_response_time_minutes: number | null;
  };
}

// Workflows
export interface WorkflowSummary {
  uuid: string;
  name: string;
  workflow_type: string | null;
  indicator_types: string[];
  state: string;
  code_version: number;
  is_active: boolean;
  is_system: boolean;
  tags: string[];
  time_saved_minutes: number | null;
  requires_approval: boolean;
  risk_level: string;
  documentation: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkflowResponse extends WorkflowSummary {
  code: string;
  timeout_seconds: number;
  retry_count: number;
  approval_channel: string | null;
  approval_timeout_seconds: number;
}

export interface WorkflowRun {
  uuid: string;
  workflow_id: number;
  trigger_type: string;
  trigger_context: Record<string, unknown> | null;
  code_version_executed: number;
  status: string;
  attempt_count: number;
  log_output: string | null;
  result: Record<string, unknown> | null;
  duration_ms: number | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkflowApproval {
  uuid: string;
  workflow_id: number;
  trigger_type: string;
  trigger_context: Record<string, unknown> | null;
  reason: string;
  confidence: number;
  notifier_type: string;
  notifier_channel: string | null;
  status: string;
  responder_id: string | null;
  responded_at: string | null;
  expires_at: string;
  execution_result: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

// Detection Rules
export interface DetectionRule {
  uuid: string;
  name: string;
  source_rule_id: string | null;
  source_name: string | null;
  severity: string | null;
  is_active: boolean;
  mitre_tactics: string[];
  mitre_techniques: string[];
  mitre_subtechniques: string[];
  data_sources: string[];
  run_frequency: string | null;
  created_by: string | null;
  documentation: string | null;
  created_at: string;
  updated_at: string;
}

// Source Integrations
export interface SourceIntegration {
  uuid: string;
  source_name: string;
  display_name: string;
  is_active: boolean;
  auth_type: string | null;
  documentation: string | null;
  created_at: string;
  updated_at: string;
}

// Agent Registrations
export interface AgentRegistration {
  uuid: string;
  name: string;
  description: string | null;
  endpoint_url: string;
  auth_header_name: string | null;
  trigger_on_sources: string[];
  trigger_on_severities: string[];
  trigger_filter: Record<string, unknown> | null;
  timeout_seconds: number;
  retry_count: number;
  is_active: boolean;
  documentation: string | null;
  created_at: string;
  updated_at: string;
}

// API Keys
export interface ApiKeyResponse {
  uuid: string;
  key_prefix: string;
  name: string;
  scopes: string[];
  allowed_sources: string[] | null;
  is_active: boolean;
  expires_at: string | null;
  last_used_at: string | null;
  created_at: string;
}

export interface ApiKeyCreateResponse {
  key: string;
  uuid: string;
  key_prefix: string;
  name: string;
  scopes: string[];
}

// Relationship Graph
export interface GraphAlertNode {
  uuid: string;
  title: string;
  severity: string;
  status: string;
  source_name: string;
  occurred_at: string;
  tags: string[];
}

export interface GraphIndicatorNode {
  uuid: string;
  type: string;
  value: string;
  malice: string;
  first_seen: string;
  last_seen: string;
  is_enriched: boolean;
  enrichment_summary: Record<string, string>;
  total_alert_count: number;
  sibling_alerts: GraphAlertNode[];
}

export interface AlertRelationshipGraph {
  alert: GraphAlertNode;
  indicators: GraphIndicatorNode[];
}

// Health
export interface HealthResponse {
  status: string;
  version: string;
  database: string;
  queue: string;
}
