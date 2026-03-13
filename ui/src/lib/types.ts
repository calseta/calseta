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
  | "Open"
  | "Triaging"
  | "Escalated"
  | "Closed";

export type EnrichmentStatus =
  | "Pending"
  | "Enriched"
  | "Failed";

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
  enrichment_status: EnrichmentStatus;
  source_name: string;
  occurred_at: string;
  ingested_at: string;
  is_enriched: boolean;
  duplicate_count: number;
  tags: string[];
  close_classification: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AlertResponse extends AlertSummary {
  enriched_at: string | null;
  fingerprint: string | null;
  close_classification: AlertCloseClassification | null;
  acknowledged_at: string | null;
  triaged_at: string | null;
  closed_at: string | null;
  detection_rule_id: number | null;
  detection_rule: DetectionRule | null;
  malice: string | null;
  malice_override: string | null;
  malice_override_source: string | null;
  malice_override_at: string | null;
  indicators: EnrichedIndicator[];
  agent_findings: AgentFinding[] | null;
  raw_payload: Record<string, unknown> | null;
  updated_at: string;
}

export type MaliceLevel = "Pending" | "Benign" | "Suspicious" | "Malicious";

export interface EnrichedIndicator {
  uuid: string;
  type: string;
  value: string;
  first_seen: string;
  last_seen: string;
  is_enriched: boolean;
  malice: string;
  malice_source: string | null;
  malice_overridden_at: string | null;
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

// Indicator Types
export const INDICATOR_TYPES = [
  "ip", "domain", "hash_md5", "hash_sha1", "hash_sha256", "url", "email", "account",
] as const;

export type IndicatorType = (typeof INDICATOR_TYPES)[number];

// Indicator detail (includes raw enrichment data)
export interface IndicatorDetailResponse {
  uuid: string;
  type: string;
  value: string;
  malice: string;
  malice_source: string | null;
  malice_overridden_at: string | null;
  first_seen: string;
  last_seen: string;
  is_enriched: boolean;
  enrichment_results: Record<string, ProviderEnrichmentResult> | null;
  created_at: string;
  updated_at: string;
}

export interface ProviderEnrichmentResult {
  success: boolean;
  enriched_at: string | null;
  extracted: Record<string, unknown> | null;
  raw: Record<string, unknown> | null;
  [key: string]: unknown;
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

// Queue metrics
export interface QueueEntry {
  queue: string;
  pending: number;
  in_progress: number;
  succeeded_30d: number;
  failed_30d: number;
  avg_duration_seconds: number | null;
  oldest_pending_age_seconds: number | null;
}

export interface QueueMetrics {
  queues: QueueEntry[];
  total_pending: number;
  total_in_progress: number;
  total_failed_30d: number;
  total_succeeded_30d: number;
  oldest_pending_age_seconds: number | null;
}

// Metrics
export interface MetricsSummary {
  period: string;
  platform: {
    context_documents: number;
    detection_rules: number;
    enrichment_providers: number;
    enrichment_providers_by_indicator_type: Record<string, number>;
    agents: number;
    workflows: number;
    indicator_mappings: number;
  };
  alerts: {
    total: number;
    active: number;
    by_severity: Record<string, number>;
    by_status: Record<string, number>;
    by_source: Record<string, number>;
    false_positive_rate: number;
    enrichment_coverage: number;
    mttd_seconds: number | null;
    mtta_seconds: number | null;
    mttt_seconds: number | null;
    mttc_seconds: number | null;
    mean_time_to_enrich_seconds: number | null;
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
  queue: QueueMetrics | null;
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
  approval_mode: string;
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
  workflow_name: string | null;
  workflow_uuid: string | null;
  trigger_type: string;
  trigger_agent_key_prefix: string | null;
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

// Enrichment Providers
export interface EnrichmentProvider {
  uuid: string;
  provider_name: string;
  display_name: string;
  description: string | null;
  is_builtin: boolean;
  is_active: boolean;
  supported_indicator_types: string[];
  http_config: Record<string, unknown>;
  auth_type: string;
  has_credentials: boolean;
  is_configured: boolean;
  env_var_mapping: Record<string, string> | null;
  default_cache_ttl_seconds: number;
  cache_ttl_by_type: Record<string, number> | null;
  malice_rules: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface HttpStepDebug {
  step_name: string;
  step_index: number;
  indicator_value: string | null;
  request_method: string;
  request_url: string;
  request_headers: Record<string, string>;
  request_query_params: Record<string, string> | null;
  request_body: unknown | null;
  response_status_code: number | null;
  response_headers: Record<string, string> | null;
  response_body: unknown | null;
  duration_ms: number;
  error: string | null;
  skipped: boolean;
}

export interface EnrichmentProviderTestResult {
  success: boolean;
  provider_name: string;
  indicator_type: string;
  indicator_value: string;
  extracted: Record<string, unknown> | null;
  raw_response: Record<string, unknown> | null;
  error_message: string | null;
  duration_ms: number;
  steps: HttpStepDebug[] | null;
}

// Enrichment Field Extractions
export interface EnrichmentFieldExtraction {
  uuid: string;
  provider_name: string;
  indicator_type: string;
  source_path: string;
  target_key: string;
  value_type: string;
  is_system: boolean;
  is_active: boolean;
  description: string | null;
  created_at: string;
  updated_at: string;
}

// Indicator Field Mappings
export interface IndicatorFieldMapping {
  uuid: string;
  source_name: string | null;
  field_path: string;
  indicator_type: string;
  extraction_target: string;
  is_system: boolean;
  is_active: boolean;
  description: string | null;
  created_at: string;
  updated_at: string;
}

// Test Extraction
export interface TestExtractionIndicator {
  type: string;
  value: string;
  source_field: string | null;
}

export interface TestExtractionPassResult {
  pass_name: string;
  pass_label: string;
  indicators: TestExtractionIndicator[];
  error: string | null;
}

export interface TestExtractionResult {
  success: boolean;
  source_name: string;
  passes: TestExtractionPassResult[];
  deduplicated: TestExtractionIndicator[];
  deduplicated_count: number;
  normalization_preview: Record<string, unknown> | null;
  error_message: string | null;
  duration_ms: number;
}

// Settings
export interface ApprovalDefaults {
  notifier: string;
  default_channel: string | null;
  default_timeout_seconds: number;
  slack_configured: boolean;
  teams_configured: boolean;
}

// Health
export interface HealthResponse {
  status: string;
  version: string;
  database: string;
  queue: string;
  queue_depth: number;
  enrichment_providers: Record<string, string>;
}

export interface DetectionRuleMetrics {
  detection_rule_uuid: string;
  detection_rule_name: string;
  period_from: string;
  period_to: string;
  total_alerts: number;
  active_alerts: number;
  alerts_by_status: Record<string, number>;
  alerts_by_severity: Record<string, number>;
  false_positive_rate: number;
  true_positive_rate: number;
  close_classifications: Record<string, number>;
  alerts_over_time: { date: string; count: number }[];
  fp_over_time: { date: string; count: number }[];
  mtta_seconds: number | null;
  mttc_seconds: number | null;
  severity_distribution: Record<string, number>;
  top_indicators: { type: string; value: string; count: number; malice: string }[];
  alert_sources: Record<string, number>;
}
