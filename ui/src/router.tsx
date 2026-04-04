import {
  createRouter,
  createRootRoute,
  createRoute,
  Outlet,
} from "@tanstack/react-router";
import { DashboardPage } from "@/pages/dashboard";
import { AlertsListPage } from "@/pages/alerts";
import { AlertDetailPage } from "@/pages/alerts/detail";
import { WorkflowsListPage } from "@/pages/workflows";
import { WorkflowDetailPage } from "@/pages/workflows/detail";
import { ApprovalsPage } from "@/pages/workflows/approvals";
import { DetectionRulesPage } from "@/pages/settings/detection-rules";
import { DetectionRuleDetailPage } from "@/pages/settings/detection-rules/detail";
import { ContextDocsPage } from "@/pages/settings/context-docs";
import { ContextDocDetailPage } from "@/pages/settings/context-docs/detail";
import { SourcesPage } from "@/pages/settings/sources";
import { AgentsPage } from "@/pages/settings/agents/index";
import { AgentDetailPage } from "@/pages/settings/agents/detail";
import { EnrichmentProvidersPage } from "@/pages/settings/enrichment-providers";
import { EnrichmentProviderDetailPage } from "@/pages/settings/enrichment-providers/detail";
import { ApiKeysPage } from "@/pages/settings/api-keys";
import { ApiKeyDetailPage } from "@/pages/settings/api-keys/detail";
import { IndicatorMappingsPage } from "@/pages/settings/indicator-mappings";
import { QueuePage } from "@/pages/queue";
import { LLMIntegrationsPage } from "@/pages/manage/llm-integrations";
import { LLMIntegrationDetailPage } from "@/pages/manage/llm-integrations/detail";
import { CampaignsPage } from "@/pages/manage/campaigns/index";
import { CampaignDetailPage } from "@/pages/manage/campaigns/detail";
import { TopologyPage } from "@/pages/manage/topology/index";
import { SecretsPage } from "@/pages/settings/secrets/index";
import { IssuesPage } from "@/pages/manage/issues/index";
import { IssueDetailPage } from "@/pages/manage/issues/detail";
import { RoutinesPage } from "@/pages/manage/routines/index";
import { RoutineDetailPage } from "@/pages/manage/routines/detail";
import { KBPage } from "@/pages/manage/kb/index";
import { KBDetailPage } from "@/pages/manage/kb/detail";
import { KBEditorPage } from "@/pages/manage/kb/editor";

const rootRoute = createRootRoute({
  component: Outlet,
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: DashboardPage,
});

const alertsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/alerts",
  component: AlertsListPage,
});

const alertDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/alerts/$uuid",
  component: AlertDetailPage,
  validateSearch: (search: Record<string, unknown>) => ({
    tab: (search.tab as string) || "indicators",
  }),
});

const workflowsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/workflows",
  component: WorkflowsListPage,
});

const workflowDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/workflows/$uuid",
  component: WorkflowDetailPage,
  validateSearch: (search: Record<string, unknown>) => ({
    tab: (search.tab as string) || undefined,
  }),
});

const approvalsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/approvals",
  component: ApprovalsPage,
});

// Manage routes
const detectionRulesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manage/detection-rules",
  component: DetectionRulesPage,
});

const detectionRuleDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manage/detection-rules/$uuid",
  component: DetectionRuleDetailPage,
  validateSearch: (search: Record<string, unknown>) => ({
    tab: (search.tab as string) || "documentation",
  }),
});

const contextDocsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manage/context-docs",
  component: ContextDocsPage,
});

const contextDocDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manage/context-docs/$uuid",
  component: ContextDocDetailPage,
  validateSearch: (search: Record<string, unknown>) => ({
    tab: (search.tab as string) || "content",
  }),
});

const agentsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manage/agents",
  component: AgentsPage,
});

const agentDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manage/agents/$uuid",
  component: AgentDetailPage,
  validateSearch: (search: Record<string, unknown>) => ({
    tab: (search.tab as string) || "configuration",
  }),
});

const enrichmentProvidersRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manage/enrichment-providers",
  component: EnrichmentProvidersPage,
});

const enrichmentProviderDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manage/enrichment-providers/$uuid",
  component: EnrichmentProviderDetailPage,
});

// Settings routes
const sourcesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings/alert-sources",
  component: SourcesPage,
});

const apiKeysRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings/api-keys",
  component: ApiKeysPage,
});

const apiKeyDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings/api-keys/$uuid",
  component: ApiKeyDetailPage,
});

const indicatorMappingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings/indicator-mappings",
  component: IndicatorMappingsPage,
});

const queueRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/queue",
  component: QueuePage,
});

const llmIntegrationsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manage/llm-integrations",
  component: LLMIntegrationsPage,
});

const llmIntegrationDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manage/llm-integrations/$uuid",
  component: LLMIntegrationDetailPage,
});

const campaignsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manage/campaigns",
  component: CampaignsPage,
});

const campaignDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manage/campaigns/$uuid",
  component: CampaignDetailPage,
});

const topologyRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manage/topology",
  component: TopologyPage,
});

const secretsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings/secrets",
  component: SecretsPage,
});

const issuesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manage/issues",
  component: IssuesPage,
});

const issueDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manage/issues/$uuid",
  component: IssueDetailPage,
  validateSearch: (search: Record<string, unknown>) => ({
    tab: (search.tab as string) || "details",
  }),
});

const routinesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manage/routines",
  component: RoutinesPage,
});

const routineDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manage/routines/$uuid",
  component: RoutineDetailPage,
  validateSearch: (search: Record<string, unknown>) => ({
    tab: (search.tab as string) || "configuration",
  }),
});

const kbRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manage/kb",
  component: KBPage,
});

const kbNewRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manage/kb/new",
  component: KBEditorPage,
});

const kbDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manage/kb/$uuid",
  component: KBDetailPage,
  validateSearch: (search: Record<string, unknown>) => ({
    slug: (search.slug as string) || undefined,
    tab: (search.tab as string) || "content",
  }),
});

const kbDetailEditRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/manage/kb/$uuid/edit",
  component: KBEditorPage,
  validateSearch: (search: Record<string, unknown>) => ({
    slug: (search.slug as string) || undefined,
  }),
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  alertsRoute,
  alertDetailRoute,
  workflowsRoute,
  workflowDetailRoute,
  approvalsRoute,
  detectionRulesRoute,
  detectionRuleDetailRoute,
  contextDocsRoute,
  contextDocDetailRoute,
  sourcesRoute,
  enrichmentProvidersRoute,
  enrichmentProviderDetailRoute,
  agentsRoute,
  agentDetailRoute,
  apiKeysRoute,
  apiKeyDetailRoute,
  indicatorMappingsRoute,
  queueRoute,
  llmIntegrationsRoute,
  llmIntegrationDetailRoute,
  campaignsRoute,
  campaignDetailRoute,
  topologyRoute,
  secretsRoute,
  issuesRoute,
  issueDetailRoute,
  routinesRoute,
  routineDetailRoute,
  kbRoute,
  kbNewRoute,
  kbDetailRoute,
  kbDetailEditRoute,
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
