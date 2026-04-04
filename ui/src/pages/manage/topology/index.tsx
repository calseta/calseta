import { useState, useCallback } from "react";
import { Link } from "@tanstack/react-router";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useTopology } from "@/hooks/use-api";
import { relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { RefreshCw } from "lucide-react";
import type { TopologyNode } from "@/lib/types";

const AGENT_TYPE_STYLES: Record<string, { background: string; border: string }> = {
  orchestrator: { background: "#0d4f3c", border: "#1a7a5e" },
  specialist: { background: "#1a3a2a", border: "#2d6b4a" },
  resolver: { background: "#2a1a3a", border: "#5a3a7a" },
  external: { background: "#2a2a2a", border: "#404040" },
};

function getNodeStyle(agentType: string): React.CSSProperties {
  const s = AGENT_TYPE_STYLES[agentType] ?? { background: "#1a2a1a", border: "#2d4a2d" };
  return {
    background: s.background,
    border: `1px solid ${s.border}`,
    borderRadius: "6px",
    padding: "10px 14px",
    color: "#e5e7eb",
    fontSize: "12px",
    minWidth: "160px",
    cursor: "pointer",
  };
}

function nodeStatusColor(status: string): string {
  switch (status) {
    case "active":
      return "text-teal bg-teal/10 border-teal/30";
    case "idle":
      return "text-dim bg-dim/10 border-dim/30";
    case "error":
      return "text-red-threat bg-red-threat/10 border-red-threat/30";
    case "paused":
      return "text-amber bg-amber/10 border-amber/30";
    default:
      return "text-muted-foreground bg-muted/50 border-muted";
  }
}

function getEdgeStyle(edgeType: string): Partial<Edge> {
  switch (edgeType) {
    case "routes_to":
      return { style: { stroke: "#1a7a5e", strokeWidth: 2 }, animated: false };
    case "delegates_to":
      return {
        style: { stroke: "#1a7a5e", strokeWidth: 2, strokeDasharray: "6 3" },
        animated: true,
      };
    case "capability":
      return { style: { stroke: "#6b7280", strokeWidth: 1, strokeDasharray: "2 4" } };
    default:
      return { style: { stroke: "#4b5563", strokeWidth: 1 } };
  }
}

function NodeLabel({ node }: { node: TopologyNode }) {
  return (
    <div className="space-y-1">
      <p className="font-medium text-sm leading-tight">{node.name}</p>
      <p className="text-[10px] opacity-70">
        {node.role ?? node.agent_type} · {node.status}
      </p>
    </div>
  );
}

function NodeDetailSheet({
  node,
  open,
  onOpenChange,
}: {
  node: TopologyNode | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  if (!node) return null;

  const budgetDollars =
    node.budget_monthly_cents !== null ? (node.budget_monthly_cents / 100).toFixed(2) : null;
  const spentDollars = (node.spent_monthly_cents / 100).toFixed(2);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-80 overflow-y-auto">
        <SheetHeader className="pb-2">
          <SheetTitle className="text-base">{node.name}</SheetTitle>
        </SheetHeader>
        <div className="space-y-4 px-4 pb-4">
          <div className="flex flex-wrap gap-1.5">
            <Badge variant="outline" className={cn("text-[10px]", nodeStatusColor(node.status))}>
              {node.status}
            </Badge>
            <Badge variant="outline" className="text-[10px] text-dim border-dim/30">
              {node.agent_type}
            </Badge>
            <Badge variant="outline" className="text-[10px] text-dim border-dim/30">
              {node.execution_mode}
            </Badge>
          </div>

          <dl className="space-y-2 text-sm">
            {node.role && (
              <div className="flex justify-between">
                <dt className="text-dim">Role</dt>
                <dd className="text-foreground">{node.role}</dd>
              </div>
            )}
            <div className="flex justify-between">
              <dt className="text-dim">Active Assignments</dt>
              <dd className="text-foreground tabular-nums">
                {node.active_assignments} / {node.max_concurrent_alerts}
              </dd>
            </div>
            {budgetDollars !== null && (
              <div className="flex justify-between">
                <dt className="text-dim">Budget (monthly)</dt>
                <dd className="text-foreground tabular-nums">${budgetDollars}</dd>
              </div>
            )}
            <div className="flex justify-between">
              <dt className="text-dim">Spent (monthly)</dt>
              <dd className="text-foreground tabular-nums">${spentDollars}</dd>
            </div>
            {node.last_heartbeat_at && (
              <div className="flex justify-between">
                <dt className="text-dim">Last Heartbeat</dt>
                <dd className="text-foreground">{relativeTime(node.last_heartbeat_at)}</dd>
              </div>
            )}
          </dl>

          {node.capabilities.length > 0 && (
            <div>
              <p className="text-[11px] text-dim uppercase tracking-wide mb-1.5">Capabilities</p>
              <div className="flex flex-wrap gap-1">
                {node.capabilities.map((cap) => (
                  <Badge
                    key={cap}
                    variant="outline"
                    className="text-[10px] text-dim border-dim/30"
                  >
                    {cap}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          <Link
            to="/manage/agents/$uuid"
            params={{ uuid: node.uuid }}
            search={{ tab: "configuration" }}
            className="block text-sm text-teal hover:text-teal-light transition-colors"
          >
            View agent details →
          </Link>
        </div>
      </SheetContent>
    </Sheet>
  );
}

function TopologyLegend() {
  return (
    <div className="absolute bottom-4 left-4 z-10 bg-card border border-border rounded-lg p-3 space-y-2 shadow-md">
      <p className="text-[10px] text-dim uppercase tracking-wide font-medium">Legend</p>
      <div className="space-y-1.5">
        {Object.entries(AGENT_TYPE_STYLES).map(([type, s]) => (
          <div key={type} className="flex items-center gap-2">
            <div
              className="h-3 w-3 rounded-sm border"
              style={{ background: s.background, borderColor: s.border }}
            />
            <span className="text-[11px] text-dim capitalize">{type}</span>
          </div>
        ))}
      </div>
      <div className="border-t border-border pt-2 space-y-1.5">
        <div className="flex items-center gap-2">
          <div className="h-0.5 w-6 bg-teal" />
          <span className="text-[11px] text-dim">routes_to</span>
        </div>
        <div className="flex items-center gap-2">
          <div
            className="h-0.5 w-6 bg-teal"
            style={{ backgroundImage: "repeating-linear-gradient(90deg,#1a7a5e 0 6px,transparent 6px 9px)" }}
          />
          <span className="text-[11px] text-dim">delegates_to</span>
        </div>
        <div className="flex items-center gap-2">
          <div
            className="h-0.5 w-6 bg-muted-foreground"
            style={{ backgroundImage: "repeating-linear-gradient(90deg,#6b7280 0 2px,transparent 2px 6px)" }}
          />
          <span className="text-[11px] text-dim">capability</span>
        </div>
      </div>
    </div>
  );
}

export function TopologyPage() {
  const { data, isLoading, refetch, isFetching } = useTopology();
  const [selectedNode, setSelectedNode] = useState<TopologyNode | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);

  const topology = data?.data;

  const rfNodes: Node[] = (topology?.nodes ?? []).map((n, i) => ({
    id: n.uuid,
    position: { x: (i % 4) * 250, y: Math.floor(i / 4) * 150 },
    data: { label: <NodeLabel node={n} />, node: n },
    style: getNodeStyle(n.agent_type),
    draggable: false,
  }));

  const rfEdges: Edge[] = (topology?.edges ?? []).map((e, i) => ({
    id: `${e.from_uuid}-${e.to_uuid}-${i}`,
    source: e.from_uuid,
    target: e.to_uuid,
    label: e.label ?? undefined,
    ...getEdgeStyle(e.edge_type),
  }));

  const onNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      const topNode = topology?.nodes.find((n) => n.uuid === node.id);
      if (topNode) {
        setSelectedNode(topNode);
        setSheetOpen(true);
      }
    },
    [topology],
  );

  return (
    <AppLayout title="Agent Topology">
      <div className="space-y-3">
        {/* Top bar */}
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => refetch()}
              disabled={isFetching}
              className="h-8 w-8 p-0 text-dim hover:text-teal"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
            </Button>
            {topology && (
              <span className="text-[11px] text-dim">
                {topology.nodes.length} node{topology.nodes.length !== 1 ? "s" : ""} ·{" "}
                {topology.edges.length} edge{topology.edges.length !== 1 ? "s" : ""}
              </span>
            )}
          </div>
        </div>

        {/* Flow canvas */}
        {isLoading ? (
          <Skeleton className="h-[600px] w-full rounded-lg" />
        ) : topology && topology.nodes.length === 0 ? (
          <Card>
            <CardContent className="py-24 text-center">
              <p className="text-sm text-dim">No agents registered</p>
            </CardContent>
          </Card>
        ) : (
          <div className="relative h-[600px] w-full rounded-lg border border-border overflow-hidden bg-card">
            <ReactFlow
              nodes={rfNodes}
              edges={rfEdges}
              onNodeClick={onNodeClick}
              nodesDraggable={false}
              nodesConnectable={false}
              elementsSelectable={true}
              fitView
              proOptions={{ hideAttribution: true }}
            >
              <Background color="#2d3748" gap={24} size={1} />
              <Controls showInteractive={false} />
            </ReactFlow>
            <TopologyLegend />
          </div>
        )}
      </div>

      <NodeDetailSheet node={selectedNode} open={sheetOpen} onOpenChange={setSheetOpen} />
    </AppLayout>
  );
}
