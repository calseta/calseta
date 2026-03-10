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
  ApprovalDefaults,
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
    queryFn: () => api.get<HealthResponse>("/health"),
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
      alertUuid,
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
export function useApprovals(statusFilter?: string) {
  const qs = statusFilter ? `?status=${statusFilter}` : "";
  return useQuery({
    queryKey: ["approvals", statusFilter],
    queryFn: () =>
      api.get<PaginatedResponse<WorkflowApproval>>(
        `/workflow-approvals${qs}`,
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
export function useSources() {
  return useQuery({
    queryKey: ["sources"],
    queryFn: () => api.get<PaginatedResponse<SourceIntegration>>("/sources"),
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
export function useAgents() {
  return useQuery({
    queryKey: ["agents"],
    queryFn: () =>
      api.get<PaginatedResponse<AgentRegistration>>("/agents"),
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
export function useApiKeys() {
  return useQuery({
    queryKey: ["api-keys"],
    queryFn: () => api.get<PaginatedResponse<ApiKeyResponse>>("/api-keys"),
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

export function useDeleteIndicatorMapping() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (uuid: string) => api.delete(`/indicator-mappings/${uuid}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["indicator-mappings"] }),
  });
}
