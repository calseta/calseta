import { useState, useCallback, useRef } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertTriangle } from "lucide-react";
import { useAlertRelationshipGraph } from "@/hooks/use-api";
import { AlertCurrentNode, AlertSiblingNode } from "./alert-node";
import { IndicatorNode } from "./indicator-node";
import { GraphTooltip } from "./graph-tooltip";
import { useGraphLayout } from "./use-graph-layout";
import type { GraphAlertNode, GraphIndicatorNode } from "@/lib/types";

const nodeTypes = {
  alertCurrent: AlertCurrentNode,
  alertSibling: AlertSiblingNode,
  indicator: IndicatorNode,
};

interface AlertGraphProps {
  alertUuid: string;
}

type TooltipState = {
  type: "alert" | "indicator";
  data: GraphAlertNode | GraphIndicatorNode;
  position: { x: number; y: number };
} | null;

export function AlertGraph({ alertUuid }: AlertGraphProps) {
  const { data, isLoading } = useAlertRelationshipGraph(alertUuid);
  const graph = data?.data;
  const { nodes, edges } = useGraphLayout(graph);

  const [tooltip, setTooltip] = useState<TooltipState>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const onNodeMouseEnter: NodeMouseHandler = useCallback((event, node) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      const rect = (event.target as HTMLElement).closest(".react-flow")?.getBoundingClientRect();
      if (!rect) return;
      const tooltipType = node.type === "indicator" ? "indicator" : "alert";
      setTooltip({
        type: tooltipType,
        data: node.data as unknown as GraphAlertNode | GraphIndicatorNode,
        position: {
          x: event.clientX - rect.left,
          y: event.clientY - rect.top,
        },
      });
    }, 150);
  }, []);

  const onNodeMouseLeave = useCallback(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    setTooltip(null);
  }, []);

  if (isLoading) {
    return (
      <div className="space-y-4 py-8">
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!graph || graph.indicators.length === 0) {
    return (
      <div className="flex items-center justify-center py-16 text-sm text-dim">
        <AlertTriangle className="h-4 w-4 mr-2" />
        No indicators to graph
      </div>
    );
  }

  return (
    <div className="relative h-[600px] w-full rounded-lg border border-border bg-surface">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeMouseEnter={onNodeMouseEnter}
        onNodeMouseLeave={onNodeMouseLeave}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        minZoom={0.3}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="var(--color-border)" gap={20} size={1} />
        <Controls
          showInteractive={false}
          className="!bg-card !border-border !shadow-none [&>button]:!bg-card [&>button]:!border-border [&>button]:!text-dim [&>button:hover]:!text-teal"
        />
      </ReactFlow>
      {tooltip && (
        <GraphTooltip
          type={tooltip.type}
          data={tooltip.data}
          position={tooltip.position}
        />
      )}
    </div>
  );
}
