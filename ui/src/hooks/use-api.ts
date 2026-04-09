import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type {
  DataResponse,
  PaginatedResponse,
  AlertSummary,
  AlertResponse,
  AlertRelationshipGraph,
  IndicatorDetailResponse,
  MetricsSummary,
  WorkflowSummary,
  WorkflowResponse,
  WorkflowRun,
  WorkflowApproval,
  DetectionRule,
  ContextDocument,
  SourceIntegration,
  AgentRegistration,
  ApiKeyResponse,
  ActivityEvent,
  HealthResponse,
  EnrichmentProvider,
  EnrichmentProviderTestResult,
  EnrichmentFieldExtraction,
  IndicatorFieldMapping,
  TestExtractionResult,
  ApprovalDefaults,
  DetectionRuleMetrics,
  LLMIntegration,
  LLMUsage,
  AlertAssignment,
  HeartbeatRun,
  CostEvent,
  CostSummary,
  AgentInvocation,
  AgentIssue,
  IssueComment,
  Routine,
  RoutineTrigger,
  RoutineRun,
  TopologyGraph,
  Secret,
  AgentAction,
  ControlPlaneDashboard,
  AgentKey,
  AgentKeyCreated,
  KBPageSummary,
  KBPageResponse,
  KBPageRevision,
  KBFolderNode,
  KBSearchResult,
  KBSyncResult,
  KBPageLink,
  AgentTool,
} from "@/lib/types";

// Settings
export function useApprovalDefaults() {
  return useQuery({
    queryKey: ["settings", "approval-defaults"],
    queryFn: () => api.get<DataResponse<ApprovalDefaults>>("/settings/approval-defaults"),
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
}

// Health
export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      const res = await fetch("/health");
      if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
      return res.json() as Promise<HealthResponse>;
    },
    refetchInterval: 30000,
    retry: 1,
  });
}

// Metrics
export function useMetricsSummary() {
  return useQuery({
    queryKey: ["metrics", "summary"],
    queryFn: () => api.get<DataResponse<MetricsSummary>>("/metrics/summary"),
  });
}

// Alerts
export function useAlerts(params: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") search.set(k, String(v));
  }
  const qs = search.toString();
  return useQuery({
    queryKey: ["alerts", qs],
    queryFn: () => api.get<PaginatedResponse<AlertSummary>>(`/alerts${qs ? `?${qs}` : ""}`),
  });
}

export function useAlert(uuid: string) {
  return useQuery({
    queryKey: ["alert", uuid],
    queryFn: () => api.get<DataResponse<AlertResponse>>(`/alerts/${uuid}`),
    enabled: !!uuid,
  });
}

export function useAlertActivity(uuid: string) {
  return useQuery({
    queryKey: ["alert-activity", uuid],
    queryFn: () =>
      api.get<PaginatedResponse<ActivityEvent>>(
        `/alerts/${uuid}/activity?page_size=100`,
      ),
    enabled: !!uuid,
  });
}

export function useAlertContext(uuid: string) {
  return useQuery({
    queryKey: ["alert-context", uuid],
    queryFn: () =>
      api.get<DataResponse<ContextDocument[]>>(`/alerts/${uuid}/context`),
    enabled: !!uuid,
  });
}

export function useAlertRelationshipGraph(uuid: string, enabled: boolean = true) {
  return useQuery({
    queryKey: ["alert-relationship-graph", uuid],
    queryFn: () =>
      api.get<DataResponse<AlertRelationshipGraph>>(
        `/alerts/${uuid}/relationship-graph`,
      ),
    enabled: !!uuid && enabled,
    staleTime: 60_000,
  });
}

export function usePatchAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uuid, body }: { uuid: string; body: Record<string, unknown> }) =>
      api.patch<DataResponse<AlertResponse>>(`/alerts/${uuid}`, body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["alert", vars.uuid] });
      qc.invalidateQueries({ queryKey: ["alerts"] });
    },
  });
}

export function useAddIndicators() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      uuid,
      indicators,
      enrich = true,
    }: {
      uuid: string;
      indicators: { type: string; value: string }[];
      enrich?: boolean;
    }) =>
      api.post<DataResponse<{ added_count: number; indicators: unknown[]; enrich_requested: boolean }>>(
        `/alerts/${uuid}/indicators?enrich=${enrich}`,
        { indicators },
      ),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["alert", vars.uuid] });
      qc.invalidateQueries({ queryKey: ["alerts"] });
      qc.invalidateQueries({ queryKey: ["alert-activity", vars.uuid] });
      qc.invalidateQueries({ queryKey: ["alert-relationship-graph", vars.uuid] });
    },
  });
}

export function useEnrichAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) =>
      api.post<DataResponse<{ message: string }>>(`/alerts/${uuid}/enrich`, {}),
    onSuccess: (_data, uuid) => {
      qc.invalidateQueries({ queryKey: ["alert", uuid] });
      qc.invalidateQueries({ queryKey: ["alert-activity", uuid] });
    },
  });
}

export function useIndicatorDetail(uuid: string | null) {
  return useQuery({
    queryKey: ["indicator", uuid],
    queryFn: () =>
      api.get<DataResponse<IndicatorDetailResponse>>(`/indicators/${uuid}`),
    enabled: !!uuid,
  });
}

export function usePatchIndicator() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      uuid,
      body,
      alertUuid: _alertUuid,
    }: {
      uuid: string;
      body: Record<string, unknown>;
      alertUuid?: string;
    }) => api.patch<DataResponse<IndicatorDetailResponse>>(`/indicators/${uuid}`, body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["indicator", vars.uuid] });
      if (vars.alertUuid) {
        qc.invalidateQueries({ queryKey: ["alert", vars.alertUuid] });
        qc.invalidateQueries({ queryKey: ["alert-activity", vars.alertUuid] });
      }
      qc.invalidateQueries({ queryKey: ["alerts"] });
    },
  });
}

// Workflows
export function useWorkflows(params?: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") search.set(k, String(v));
    }
  }
  const qs = search.toString();
  return useQuery({
    queryKey: ["workflows", qs],
    queryFn: () =>
      api.get<PaginatedResponse<WorkflowSummary>>(`/workflows${qs ? `?${qs}` : ""}`),
  });
}

export function useCreateWorkflow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<DataResponse<WorkflowResponse>>("/workflows", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workflows"] }),
  });
}

export function useWorkflow(uuid: string) {
  return useQuery({
    queryKey: ["workflow", uuid],
    queryFn: () => api.get<DataResponse<WorkflowResponse>>(`/workflows/${uuid}`),
    enabled: !!uuid,
  });
}

export function useWorkflowRuns(uuid: string) {
  return useQuery({
    queryKey: ["workflow-runs", uuid],
    queryFn: () =>
      api.get<PaginatedResponse<WorkflowRun>>(
        `/workflows/${uuid}/runs?page_size=50`,
      ),
    enabled: !!uuid,
  });
}

export function usePatchWorkflow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uuid, body }: { uuid: string; body: Record<string, unknown> }) =>
      api.patch<DataResponse<WorkflowResponse>>(`/workflows/${uuid}`, body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["workflow", vars.uuid] });
      qc.invalidateQueries({ queryKey: ["workflows"] });
    },
  });
}

export function useTestWorkflow() {
  return useMutation({
    mutationFn: ({ uuid, body }: { uuid: string; body: Record<string, unknown> }) =>
      api.post<Record<string, unknown>>(`/workflows/${uuid}/test`, body),
  });
}

export function useExecuteWorkflow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uuid, body }: { uuid: string; body: Record<string, unknown> }) =>
      api.post<Record<string, unknown>>(`/workflows/${uuid}/execute`, body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["workflow-runs", vars.uuid] });
    },
  });
}

// Approvals
export function useApprovals(params?: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") search.set(k, String(v));
    }
  }
  const qs = search.toString();
  return useQuery({
    queryKey: ["approvals", qs],
    queryFn: () =>
      api.get<PaginatedResponse<WorkflowApproval>>(
        `/workflow-approvals${qs ? `?${qs}` : ""}`,
      ),
  });
}

export function useApproveWorkflow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uuid, body }: { uuid: string; body?: Record<string, unknown> }) =>
      api.post(`/workflow-approvals/${uuid}/approve`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["approvals"] });
    },
  });
}

export function useRejectWorkflow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uuid, body }: { uuid: string; body?: Record<string, unknown> }) =>
      api.post(`/workflow-approvals/${uuid}/reject`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["approvals"] });
    },
  });
}

// Detection Rules
export function useDetectionRules(params?: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") search.set(k, String(v));
    }
  }
  const qs = search.toString();
  return useQuery({
    queryKey: ["detection-rules", qs],
    queryFn: () =>
      api.get<PaginatedResponse<DetectionRule>>(`/detection-rules${qs ? `?${qs}` : ""}`),
  });
}

export function useCreateDetectionRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<DataResponse<DetectionRule>>("/detection-rules", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["detection-rules"] }),
  });
}

export function usePatchDetectionRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uuid, body }: { uuid: string; body: Record<string, unknown> }) =>
      api.patch<DataResponse<DetectionRule>>(`/detection-rules/${uuid}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["detection-rules"] }),
  });
}

export function useDeleteDetectionRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) => api.delete(`/detection-rules/${uuid}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["detection-rules"] }),
  });
}

// Detection Rule (single)
export function useDetectionRule(uuid: string) {
  return useQuery({
    queryKey: ["detection-rule", uuid],
    queryFn: () => api.get<DataResponse<DetectionRule>>(`/detection-rules/${uuid}`),
    enabled: !!uuid,
  });
}

export function useDetectionRuleMetrics(uuid: string) {
  return useQuery({
    queryKey: ["detection-rule-metrics", uuid],
    queryFn: () =>
      api.get<DataResponse<DetectionRuleMetrics>>(`/detection-rules/${uuid}/metrics`),
    enabled: !!uuid,
  });
}

// Context Documents
export function useContextDocuments(params?: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") search.set(k, String(v));
    }
  }
  const qs = search.toString();
  return useQuery({
    queryKey: ["context-documents", qs],
    queryFn: () =>
      api.get<PaginatedResponse<ContextDocument>>(
        `/context-documents${qs ? `?${qs}` : ""}`,
      ),
  });
}

export function useCreateContextDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<DataResponse<ContextDocument>>("/context-documents", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["context-documents"] }),
  });
}

export function useContextDocument(uuid: string) {
  return useQuery({
    queryKey: ["context-document", uuid],
    queryFn: () => api.get<DataResponse<ContextDocument>>(`/context-documents/${uuid}`),
    enabled: !!uuid,
  });
}

export function usePatchContextDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uuid, body }: { uuid: string; body: Record<string, unknown> }) =>
      api.patch<DataResponse<ContextDocument>>(`/context-documents/${uuid}`, body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["context-document", vars.uuid] });
      qc.invalidateQueries({ queryKey: ["context-documents"] });
    },
  });
}

export function useDeleteContextDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) => api.delete(`/context-documents/${uuid}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["context-documents"] }),
  });
}

// Sources
export function useSources(params?: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") search.set(k, String(v));
    }
  }
  const qs = search.toString();
  return useQuery({
    queryKey: ["sources", qs],
    queryFn: () => api.get<PaginatedResponse<SourceIntegration>>(`/sources${qs ? `?${qs}` : ""}`),
  });
}

export function useCreateSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<DataResponse<SourceIntegration>>("/sources", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sources"] }),
  });
}

export function useDeleteSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) => api.delete(`/sources/${uuid}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sources"] }),
  });
}

// Agents
export function useAgents(params?: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") search.set(k, String(v));
    }
  }
  const qs = search.toString();
  return useQuery({
    queryKey: ["agents", qs],
    queryFn: () =>
      api.get<PaginatedResponse<AgentRegistration>>(`/agents${qs ? `?${qs}` : ""}`),
  });
}

export function useCreateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<DataResponse<AgentRegistration>>("/agents", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });
}

export function useDeleteAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) => api.delete(`/agents/${uuid}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });
}

export function useAgent(uuid: string) {
  return useQuery({
    queryKey: ["agent", uuid],
    queryFn: () => api.get<DataResponse<AgentRegistration>>(`/agents/${uuid}`),
    enabled: !!uuid,
  });
}

export function usePatchAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uuid, body }: { uuid: string; body: Record<string, unknown> }) =>
      api.patch<DataResponse<AgentRegistration>>(`/agents/${uuid}`, body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["agents"] });
      qc.invalidateQueries({ queryKey: ["agent", vars.uuid] });
    },
  });
}

export function useTestAgent() {
  return useMutation({
    mutationFn: (uuid: string) =>
      api.post<DataResponse<{ delivered: boolean; status_code: number | null; duration_ms: number; error: string | null }>>(`/agents/${uuid}/test`),
  });
}

export function useDispatchAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ alertUuid, agentUuid }: { alertUuid: string; agentUuid: string }) =>
      api.post<DataResponse<{ agent_uuid: string; agent_name: string; alert_uuid: string }>>(
        `/alerts/${alertUuid}/dispatch-agent?agent_uuid=${agentUuid}`,
      ),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["alert-activity", vars.alertUuid] });
    },
  });
}

// API Keys
export function useApiKeys(params?: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") search.set(k, String(v));
    }
  }
  const qs = search.toString();
  return useQuery({
    queryKey: ["api-keys", qs],
    queryFn: () => api.get<PaginatedResponse<ApiKeyResponse>>(`/api-keys${qs ? `?${qs}` : ""}`),
  });
}

export function useCreateApiKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<DataResponse<{ key: string; uuid: string; key_prefix: string }>>("/api-keys", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["api-keys"] }),
  });
}

export function useApiKey(uuid: string) {
  return useQuery({
    queryKey: ["api-key", uuid],
    queryFn: () => api.get<DataResponse<ApiKeyResponse>>(`/api-keys/${uuid}`),
    enabled: !!uuid,
  });
}

export function usePatchApiKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uuid, body }: { uuid: string; body: Record<string, unknown> }) =>
      api.patch<DataResponse<ApiKeyResponse>>(`/api-keys/${uuid}`, body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["api-key", vars.uuid] });
      qc.invalidateQueries({ queryKey: ["api-keys"] });
    },
  });
}

export function useDeactivateApiKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) =>
      api.patch(`/api-keys/${uuid}`, { is_active: false }),
    onSuccess: (_data, uuid) => {
      qc.invalidateQueries({ queryKey: ["api-key", uuid] });
      qc.invalidateQueries({ queryKey: ["api-keys"] });
    },
  });
}

// Enrichment Providers
export function useEnrichmentProviders(params?: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") search.set(k, String(v));
    }
  }
  const qs = search.toString();
  return useQuery({
    queryKey: ["enrichment-providers", qs],
    queryFn: () =>
      api.get<PaginatedResponse<EnrichmentProvider>>(`/enrichment-providers${qs ? `?${qs}` : ""}`),
  });
}

export function useEnrichmentProvider(uuid: string) {
  return useQuery({
    queryKey: ["enrichment-provider", uuid],
    queryFn: () => api.get<DataResponse<EnrichmentProvider>>(`/enrichment-providers/${uuid}`),
    enabled: !!uuid,
  });
}

export function useCreateEnrichmentProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<DataResponse<EnrichmentProvider>>("/enrichment-providers", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["enrichment-providers"] }),
  });
}

export function usePatchEnrichmentProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uuid, body }: { uuid: string; body: Record<string, unknown> }) =>
      api.patch<DataResponse<EnrichmentProvider>>(`/enrichment-providers/${uuid}`, body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["enrichment-providers"] });
      qc.invalidateQueries({ queryKey: ["enrichment-provider", vars.uuid] });
    },
  });
}

export function useDeleteEnrichmentProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) => api.delete(`/enrichment-providers/${uuid}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["enrichment-providers"] }),
  });
}

export function useActivateEnrichmentProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) =>
      api.post<DataResponse<EnrichmentProvider>>(`/enrichment-providers/${uuid}/activate`),
    onSuccess: (_data, uuid) => {
      qc.invalidateQueries({ queryKey: ["enrichment-providers"] });
      qc.invalidateQueries({ queryKey: ["enrichment-provider", uuid] });
    },
  });
}

export function useDeactivateEnrichmentProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) =>
      api.post<DataResponse<EnrichmentProvider>>(`/enrichment-providers/${uuid}/deactivate`),
    onSuccess: (_data, uuid) => {
      qc.invalidateQueries({ queryKey: ["enrichment-providers"] });
      qc.invalidateQueries({ queryKey: ["enrichment-provider", uuid] });
    },
  });
}

export function useTestEnrichmentProvider() {
  return useMutation({
    mutationFn: ({ uuid, body }: { uuid: string; body: { indicator_type: string; indicator_value: string } }) =>
      api.post<DataResponse<EnrichmentProviderTestResult>>(`/enrichment-providers/${uuid}/test`, body),
  });
}

// Enrichment Field Extractions
export function useFieldExtractions(params?: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") search.set(k, String(v));
    }
  }
  const qs = search.toString();
  return useQuery({
    queryKey: ["field-extractions", qs],
    queryFn: () =>
      api.get<PaginatedResponse<EnrichmentFieldExtraction>>(`/enrichment-field-extractions${qs ? `?${qs}` : ""}`),
  });
}

export function useCreateFieldExtraction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<DataResponse<EnrichmentFieldExtraction>>("/enrichment-field-extractions", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["field-extractions"] }),
  });
}

export function useBulkCreateFieldExtractions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<DataResponse<EnrichmentFieldExtraction[]>>("/enrichment-field-extractions/bulk", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["field-extractions"] }),
  });
}

export function usePatchFieldExtraction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uuid, body }: { uuid: string; body: Record<string, unknown> }) =>
      api.patch<DataResponse<EnrichmentFieldExtraction>>(`/enrichment-field-extractions/${uuid}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["field-extractions"] }),
  });
}

export function useDeleteFieldExtraction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) => api.delete(`/enrichment-field-extractions/${uuid}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["field-extractions"] }),
  });
}

// Indicator Field Mappings
export function useIndicatorMappings(params?: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") search.set(k, String(v));
    }
  }
  const qs = search.toString();
  return useQuery({
    queryKey: ["indicator-mappings", qs],
    queryFn: () =>
      api.get<PaginatedResponse<IndicatorFieldMapping>>(`/indicator-mappings${qs ? `?${qs}` : ""}`)
  });
}

export function useCreateIndicatorMapping() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<DataResponse<IndicatorFieldMapping>>("/indicator-mappings", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["indicator-mappings"] }),
  });
}

export function useSourcePluginFields() {
  return useQuery({
    queryKey: ["indicator-mappings", "source-plugin-fields"],
    queryFn: () =>
      api.get<DataResponse<IndicatorFieldMapping[]>>("/indicator-mappings/source-plugin-fields"),
    staleTime: 10 * 60 * 1000,
  });
}

export function useTestExtraction() {
  return useMutation({
    mutationFn: (body: { source_name: string; raw_payload: Record<string, unknown> }) =>
      api.post<DataResponse<TestExtractionResult>>("/indicator-mappings/test-extraction", body),
  });
}

export function useDeleteIndicatorMapping() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) => api.delete(`/indicator-mappings/${uuid}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["indicator-mappings"] }),
  });
}

// ============================================================
// Control Plane v2 hooks
// ============================================================

// LLM Integrations
export function useLLMIntegrations(params?: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") search.set(k, String(v));
    }
  }
  const qs = search.toString();
  return useQuery({
    queryKey: ["llm-integrations", qs],
    queryFn: () => api.get<PaginatedResponse<LLMIntegration>>(`/llm-integrations${qs ? `?${qs}` : ""}`),
  });
}

export function useLLMIntegration(uuid: string) {
  return useQuery({
    queryKey: ["llm-integration", uuid],
    queryFn: () => api.get<DataResponse<LLMIntegration>>(`/llm-integrations/${uuid}`),
    enabled: !!uuid,
  });
}

export function useCreateLLMIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<DataResponse<LLMIntegration>>("/llm-integrations", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["llm-integrations"] }),
  });
}

export function usePatchLLMIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uuid, body }: { uuid: string; body: Record<string, unknown> }) =>
      api.patch<DataResponse<LLMIntegration>>(`/llm-integrations/${uuid}`, body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["llm-integrations"] });
      qc.invalidateQueries({ queryKey: ["llm-integration", vars.uuid] });
    },
  });
}

export function useDeleteLLMIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) => api.delete(`/llm-integrations/${uuid}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["llm-integrations"] }),
  });
}

export function useLLMIntegrationUsage(uuid: string) {
  return useQuery({
    queryKey: ["llm-integration-usage", uuid],
    queryFn: () => api.get<DataResponse<LLMUsage>>(`/llm-integrations/${uuid}/usage`),
    enabled: !!uuid,
  });
}

// Alert Queue
export function useAlertQueue(params?: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") search.set(k, String(v));
    }
  }
  const qs = search.toString();
  return useQuery({
    queryKey: ["alert-queue", qs],
    queryFn: () => api.get<PaginatedResponse<AlertResponse>>(`/queue${qs ? `?${qs}` : ""}`),
    refetchInterval: 30_000,
  });
}

export function useCheckoutAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (alertUuid: string) =>
      api.post<DataResponse<AlertAssignment>>(`/queue/${alertUuid}/checkout`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alert-queue"] }),
  });
}

export function useReleaseAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (alertUuid: string) =>
      api.post<DataResponse<AlertAssignment>>(`/queue/${alertUuid}/release`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alert-queue"] }),
  });
}

// Post heartbeat (trigger for an agent by operator)
export function usePostHeartbeat() {
  return useMutation({
    mutationFn: (agentUuid: string) =>
      api.post<DataResponse<{ status: string }>>("/heartbeat", { agent_id: agentUuid }),
  });
}

// Agent Heartbeat Runs
export function useAgentHeartbeatRuns(agentUuid: string, params?: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") search.set(k, String(v));
    }
  }
  const qs = search.toString();
  return useQuery({
    queryKey: ["agent-heartbeat-runs", agentUuid, qs],
    queryFn: () => api.get<PaginatedResponse<HeartbeatRun>>(`/agents/${agentUuid}/heartbeat-runs${qs ? `?${qs}` : ""}`),
    enabled: !!agentUuid,
  });
}

// Agent Invocations
export function useAgentInvocations(agentUuid: string, params?: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") search.set(k, String(v));
    }
  }
  const qs = search.toString();
  return useQuery({
    queryKey: ["agent-invocations", agentUuid, qs],
    queryFn: () => api.get<PaginatedResponse<AgentInvocation>>(`/agents/${agentUuid}/invocations${qs ? `?${qs}` : ""}`),
    enabled: !!agentUuid,
  });
}

// Cost Events
export function useCostEvents(params?: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") search.set(k, String(v));
    }
  }
  const qs = search.toString();
  return useQuery({
    queryKey: ["cost-events", qs],
    queryFn: () => api.get<PaginatedResponse<CostEvent>>(`/cost-events${qs ? `?${qs}` : ""}`),
  });
}

export function useAgentCostEvents(agentUuid: string, params?: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") search.set(k, String(v));
    }
  }
  const qs = search.toString();
  return useQuery({
    queryKey: ["agent-cost-events", agentUuid, qs],
    queryFn: () => api.get<PaginatedResponse<CostEvent>>(`/agents/${agentUuid}/cost-events${qs ? `?${qs}` : ""}`),
    enabled: !!agentUuid,
  });
}

export function useAgentCostSummary(agentUuid: string) {
  return useQuery({
    queryKey: ["agent-cost-summary", agentUuid],
    queryFn: () => api.get<DataResponse<CostSummary>>(`/agents/${agentUuid}/cost-summary`),
    enabled: !!agentUuid,
  });
}

// Invocations (instance-wide)
export function useInvocation(uuid: string) {
  return useQuery({
    queryKey: ["invocation", uuid],
    queryFn: () => api.get<DataResponse<AgentInvocation>>(`/invocations/${uuid}`),
    enabled: !!uuid,
  });
}

// Issues
export function useIssues(params?: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") search.set(k, String(v));
    }
  }
  const qs = search.toString();
  return useQuery({
    queryKey: ["issues", qs],
    queryFn: () => api.get<PaginatedResponse<AgentIssue>>(`/issues${qs ? `?${qs}` : ""}`),
  });
}

export function useIssue(uuid: string) {
  return useQuery({
    queryKey: ["issue", uuid],
    queryFn: () => api.get<DataResponse<AgentIssue>>(`/issues/${uuid}`),
    enabled: !!uuid,
  });
}

export function useCreateIssue() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<DataResponse<AgentIssue>>("/issues", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["issues"] }),
  });
}

export function usePatchIssue() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uuid, body }: { uuid: string; body: Record<string, unknown> }) =>
      api.patch<DataResponse<AgentIssue>>(`/issues/${uuid}`, body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["issues"] });
      qc.invalidateQueries({ queryKey: ["issue", vars.uuid] });
    },
  });
}

export function useIssueComments(uuid: string) {
  return useQuery({
    queryKey: ["issue-comments", uuid],
    queryFn: () => api.get<PaginatedResponse<IssueComment>>(`/issues/${uuid}/comments`),
    enabled: !!uuid,
  });
}

export function useAddIssueComment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uuid, body }: { uuid: string; body: Record<string, unknown> }) =>
      api.post<DataResponse<IssueComment>>(`/issues/${uuid}/comments`, body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["issue-comments", vars.uuid] });
    },
  });
}

// Routines
export function useRoutines(params?: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") search.set(k, String(v));
    }
  }
  const qs = search.toString();
  return useQuery({
    queryKey: ["routines", qs],
    queryFn: () => api.get<PaginatedResponse<Routine>>(`/routines${qs ? `?${qs}` : ""}`),
  });
}

export function useRoutine(uuid: string) {
  return useQuery({
    queryKey: ["routine", uuid],
    queryFn: () => api.get<DataResponse<Routine>>(`/routines/${uuid}`),
    enabled: !!uuid,
  });
}

export function useCreateRoutine() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<DataResponse<Routine>>("/routines", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["routines"] }),
  });
}

export function usePatchRoutine() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uuid, body }: { uuid: string; body: Record<string, unknown> }) =>
      api.patch<DataResponse<Routine>>(`/routines/${uuid}`, body),
    onMutate: async (vars) => {
      await qc.cancelQueries({ queryKey: ["routine", vars.uuid] });
      const prev = qc.getQueryData<DataResponse<Routine>>(["routine", vars.uuid]);
      qc.setQueryData<DataResponse<Routine>>(["routine", vars.uuid], (old) => {
        if (!old) return old;
        return { ...old, data: { ...old.data, ...vars.body } };
      });
      return { prev };
    },
    onError: (_err, vars, ctx) => {
      if (ctx?.prev !== undefined) qc.setQueryData(["routine", vars.uuid], ctx.prev);
    },
    onSettled: (_data, _err, vars) => {
      qc.invalidateQueries({ queryKey: ["routines"] });
      qc.invalidateQueries({ queryKey: ["routine", vars.uuid] });
    },
  });
}

export function usePatchTrigger() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ routineUuid, triggerUuid, body }: { routineUuid: string; triggerUuid: string; body: Record<string, unknown> }) =>
      api.patch<DataResponse<RoutineTrigger>>(`/routines/${routineUuid}/triggers/${triggerUuid}`, body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["routine", vars.routineUuid] });
    },
  });
}

export function useTriggerRoutine() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uuid, payload }: { uuid: string; payload?: Record<string, unknown> }) =>
      api.post<DataResponse<{ message: string }>>(`/routines/${uuid}/invoke`, payload ?? {}),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["routine-runs", vars.uuid] });
      qc.invalidateQueries({ queryKey: ["routine", vars.uuid] });
    },
  });
}

export function useRoutineRuns(uuid: string) {
  return useQuery({
    queryKey: ["routine-runs", uuid],
    queryFn: () => api.get<PaginatedResponse<RoutineRun>>(`/routines/${uuid}/runs?page_size=50`),
    enabled: !!uuid,
  });
}

export function useDeleteRoutine() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) => api.delete(`/routines/${uuid}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["routines"] }),
  });
}

// Topology
export function useTopology() {
  return useQuery({
    queryKey: ["topology"],
    queryFn: () => api.get<DataResponse<TopologyGraph>>("/topology"),
    staleTime: 30_000,
  });
}

// Secrets
export function useSecrets(params?: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") search.set(k, String(v));
    }
  }
  const qs = search.toString();
  return useQuery({
    queryKey: ["secrets", qs],
    queryFn: () => api.get<PaginatedResponse<Secret>>(`/secrets${qs ? `?${qs}` : ""}`),
  });
}

export function useCreateSecret() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<DataResponse<Secret>>("/secrets", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["secrets"] }),
  });
}

export function useRotateSecret() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, value }: { name: string; value: string }) =>
      api.post<DataResponse<{ message: string }>>(`/secrets/${name}/versions`, { value }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["secrets"] }),
  });
}

export function useDeleteSecret() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) => api.delete(`/secrets/${uuid}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["secrets"] }),
  });
}

// Actions
export function useActions(params?: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") search.set(k, String(v));
    }
  }
  const qs = search.toString();
  return useQuery({
    queryKey: ["actions", qs],
    queryFn: () => api.get<PaginatedResponse<AgentAction>>(`/actions${qs ? `?${qs}` : ""}`),
  });
}

export function useAction(uuid: string) {
  return useQuery({
    queryKey: ["action", uuid],
    queryFn: () => api.get<DataResponse<AgentAction>>(`/actions/${uuid}`),
    enabled: !!uuid,
  });
}

export function usePatchAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uuid, body }: { uuid: string; body: Record<string, unknown> }) =>
      api.patch<DataResponse<AgentAction>>(`/actions/${uuid}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["actions"] }),
  });
}

export function useCancelAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) =>
      api.post<DataResponse<AgentAction>>(`/actions/${uuid}/cancel`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["actions"] }),
  });
}

// Agent lifecycle — pause / resume / terminate
export function usePauseAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ uuid, reason }: { uuid: string; reason?: string }) =>
      api.post<DataResponse<AgentRegistration>>(`/agents/${uuid}/pause`, { reason }),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["agent", vars.uuid] });
      qc.invalidateQueries({ queryKey: ["agents"] });
    },
  });
}

export function useResumeAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) =>
      api.post<DataResponse<AgentRegistration>>(`/agents/${uuid}/resume`),
    onSuccess: (_data, uuid) => {
      qc.invalidateQueries({ queryKey: ["agent", uuid] });
      qc.invalidateQueries({ queryKey: ["agents"] });
    },
  });
}

export function useTerminateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) =>
      api.post<DataResponse<AgentRegistration>>(`/agents/${uuid}/terminate`),
    onSuccess: (_data, uuid) => {
      qc.invalidateQueries({ queryKey: ["agent", uuid] });
      qc.invalidateQueries({ queryKey: ["agents"] });
    },
  });
}

// Agent API keys
export function useAgentKeys(agentUuid: string) {
  return useQuery({
    queryKey: ["agent-keys", agentUuid],
    queryFn: () => api.get<PaginatedResponse<AgentKey>>(`/agents/${agentUuid}/keys`),
    enabled: !!agentUuid,
  });
}

export function useCreateAgentKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ agentUuid, name }: { agentUuid: string; name: string }) =>
      api.post<DataResponse<AgentKeyCreated>>(`/agents/${agentUuid}/keys`, { name }),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["agent-keys", vars.agentUuid] });
    },
  });
}

export function useRevokeAgentKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ agentUuid, keyId }: { agentUuid: string; keyId: string }) =>
      api.delete(`/agents/${agentUuid}/keys/${keyId}`),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["agent-keys", vars.agentUuid] });
    },
  });
}

// Control Plane Dashboard
export function useControlPlaneDashboard() {
  return useQuery({
    queryKey: ["control-plane-dashboard"],
    queryFn: () => api.get<DataResponse<ControlPlaneDashboard>>("/dashboard"),
    refetchInterval: 30_000,
  });
}

// ============================================================
// Knowledge Base hooks
// ============================================================

export function useKBPages(params?: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") search.set(k, String(v));
    }
  }
  const qs = search.toString();
  return useQuery({
    queryKey: ["kb-pages", qs],
    queryFn: () => api.get<PaginatedResponse<KBPageSummary>>(`/kb${qs ? `?${qs}` : ""}`),
  });
}

export function useKBFolders() {
  return useQuery({
    queryKey: ["kb-folders"],
    queryFn: () => api.get<DataResponse<KBFolderNode[]>>("/kb/folders"),
    staleTime: 60_000,
  });
}

export function useKBSearch(q: string, params?: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams({ q });
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") search.set(k, String(v));
    }
  }
  return useQuery({
    queryKey: ["kb-search", q, search.toString()],
    queryFn: () => api.get<PaginatedResponse<KBSearchResult>>(`/kb/search?${search.toString()}`),
    enabled: q.length >= 1,
  });
}

export function useKBPage(slug: string) {
  return useQuery({
    queryKey: ["kb-page", slug],
    queryFn: () => api.get<DataResponse<KBPageResponse>>(`/kb/${encodeURIComponent(slug)}`),
    enabled: !!slug,
  });
}

export function useCreateKBPage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api.post<DataResponse<KBPageResponse>>("/kb", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["kb-pages"] });
      qc.invalidateQueries({ queryKey: ["kb-folders"] });
    },
  });
}

export function usePatchKBPage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, body }: { slug: string; body: Record<string, unknown> }) =>
      api.patch<DataResponse<KBPageResponse>>(`/kb/${encodeURIComponent(slug)}`, body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["kb-page", vars.slug] });
      qc.invalidateQueries({ queryKey: ["kb-pages"] });
    },
  });
}

export function useDeleteKBPage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (slug: string) => api.delete(`/kb/${encodeURIComponent(slug)}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["kb-pages"] });
      qc.invalidateQueries({ queryKey: ["kb-folders"] });
    },
  });
}

export function useKBRevisions(slug: string) {
  return useQuery({
    queryKey: ["kb-revisions", slug],
    queryFn: () => api.get<PaginatedResponse<KBPageRevision>>(`/kb/${encodeURIComponent(slug)}/revisions?page_size=50`),
    enabled: !!slug,
  });
}

export function useSyncKBPage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (slug: string) =>
      api.post<DataResponse<KBSyncResult>>(`/kb/${encodeURIComponent(slug)}/sync`),
    onSuccess: (_data, slug) => {
      qc.invalidateQueries({ queryKey: ["kb-page", slug] });
      qc.invalidateQueries({ queryKey: ["kb-pages"] });
    },
  });
}

export function useAddKBPageLink() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, body }: { slug: string; body: Record<string, unknown> }) =>
      api.post<DataResponse<KBPageLink>>(`/kb/${encodeURIComponent(slug)}/links`, body),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["kb-page", vars.slug] });
    },
  });
}

// ============================================================
// Agent Tools
// ============================================================

export function useTools(params?: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== "") search.set(k, String(v));
    }
  }
  search.set("page_size", "500");
  const qs = search.toString();
  return useQuery({
    queryKey: ["tools", qs],
    queryFn: () => api.get<PaginatedResponse<AgentTool>>(`/tools?${qs}`),
  });
}

// Agent activity (404 if endpoint not yet deployed)
export function useAgentActivity(agentUuid: string) {
  return useQuery({
    queryKey: ["agent-activity", agentUuid],
    queryFn: () => api.get<PaginatedResponse<ActivityEvent>>(`/agents/${agentUuid}/activity?page_size=10`),
    enabled: !!agentUuid,
    retry: false,
  });
}
