import { useMemo } from "react";
import type { Node, Edge } from "@xyflow/react";
import dagre from "@dagrejs/dagre";
import type { AlertRelationshipGraph } from "@/lib/types";

export interface GraphLayoutResult {
  nodes: Node[];
  edges: Edge[];
}

const NODE_WIDTH = 240;
const ALERT_NODE_HEIGHT = 80;
const INDICATOR_NODE_HEIGHT = 70;
const SIBLING_NODE_HEIGHT = 60;

export function useGraphLayout(graph: AlertRelationshipGraph | undefined): GraphLayoutResult {
  return useMemo(() => {
    if (!graph) return { nodes: [], edges: [] };

    const g = new dagre.graphlib.Graph();
    g.setDefaultEdgeLabel(() => ({}));
    g.setGraph({ rankdir: "TB", ranksep: 80, nodesep: 40 });

    const nodes: Node[] = [];
    const edges: Edge[] = [];

    // Track sibling alerts to deduplicate across indicators
    const siblingNodeIds = new Map<string, string>(); // alert uuid -> node id

    // 1) Current alert node (center)
    const alertNodeId = `alert-${graph.alert.uuid}`;
    g.setNode(alertNodeId, { width: NODE_WIDTH + 20, height: ALERT_NODE_HEIGHT });
    nodes.push({
      id: alertNodeId,
      type: "alertCurrent",
      position: { x: 0, y: 0 },
      data: graph.alert as unknown as Record<string, unknown>,
    });

    // 2) Indicator nodes
    graph.indicators.forEach((ind) => {
      const indNodeId = `indicator-${ind.uuid}`;
      g.setNode(indNodeId, { width: NODE_WIDTH, height: INDICATOR_NODE_HEIGHT });
      nodes.push({
        id: indNodeId,
        type: "indicator",
        position: { x: 0, y: 0 },
        data: ind as unknown as Record<string, unknown>,
      });

      edges.push({
        id: `e-${alertNodeId}-${indNodeId}`,
        source: alertNodeId,
        target: indNodeId,
        type: "smoothstep",
        animated: true,
        style: { stroke: "var(--color-teal)", strokeWidth: 2 },
      });

      // 3) Sibling alert nodes
      ind.sibling_alerts.forEach((sibling) => {
        let siblingNodeId = siblingNodeIds.get(sibling.uuid);
        if (!siblingNodeId) {
          siblingNodeId = `sibling-${sibling.uuid}`;
          siblingNodeIds.set(sibling.uuid, siblingNodeId);
          g.setNode(siblingNodeId, { width: NODE_WIDTH - 20, height: SIBLING_NODE_HEIGHT });
          nodes.push({
            id: siblingNodeId,
            type: "alertSibling",
            position: { x: 0, y: 0 },
            data: sibling as unknown as Record<string, unknown>,
          });
        }

        const edgeId = `e-${indNodeId}-${siblingNodeId}`;
        if (!edges.some((e) => e.id === edgeId)) {
          edges.push({
            id: edgeId,
            source: indNodeId,
            target: siblingNodeId,
            type: "smoothstep",
            style: { stroke: "var(--color-border)", strokeWidth: 1 },
          });
        }
      });
    });

    // Layout with dagre
    dagre.layout(g);

    // Apply positions from dagre
    nodes.forEach((node) => {
      const pos = g.node(node.id);
      if (pos) {
        node.position = {
          x: pos.x - (pos.width ?? NODE_WIDTH) / 2,
          y: pos.y - (pos.height ?? ALERT_NODE_HEIGHT) / 2,
        };
      }
    });

    return { nodes, edges };
  }, [graph]);
}
