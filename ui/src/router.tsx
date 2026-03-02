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
import { ApiKeysPage } from "@/pages/settings/api-keys";
import { ApiKeyDetailPage } from "@/pages/settings/api-keys/detail";

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
});

const approvalsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/approvals",
  component: ApprovalsPage,
});

const detectionRulesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings/detection-rules",
  component: DetectionRulesPage,
});

const detectionRuleDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings/detection-rules/$uuid",
  component: DetectionRuleDetailPage,
});

const contextDocsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings/context-docs",
  component: ContextDocsPage,
});

const contextDocDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings/context-docs/$uuid",
  component: ContextDocDetailPage,
});

const sourcesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings/sources",
  component: SourcesPage,
});

const agentsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings/agents",
  component: AgentsPage,
});

const agentDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings/agents/$uuid",
  component: AgentDetailPage,
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
  agentsRoute,
  agentDetailRoute,
  apiKeysRoute,
  apiKeyDetailRoute,
]);

export const router = createRouter({ routeTree });

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
