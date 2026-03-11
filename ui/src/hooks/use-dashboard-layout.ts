import { useState, useCallback } from "react";
import type { Layout } from "react-grid-layout";

// Bump version when grid columns or default card set changes.
// This discards stale layouts from localStorage automatically.
const LAYOUT_VERSION = 3;
const STORAGE_KEY = `calseta:dashboard-grid:v${LAYOUT_VERSION}`;

// 12-column grid (industry standard — divisible by 1,2,3,4,6,12).
// rowHeight=80px. Cards fill every row edge-to-edge.
const DEFAULT_LAYOUT: Layout[] = [
  // Row 0: Platform stats — 6 items × 2 cols = 12 (full row)
  { i: "ctx-docs",        x: 0,  y: 0, w: 2, h: 1, minW: 1, maxW: 4 },
  { i: "det-rules",       x: 2,  y: 0, w: 2, h: 1, minW: 1, maxW: 4 },
  { i: "enrich-prov",     x: 4,  y: 0, w: 2, h: 1, minW: 1, maxW: 4 },
  { i: "agents",          x: 6,  y: 0, w: 2, h: 1, minW: 1, maxW: 4 },
  { i: "workflows-count", x: 8,  y: 0, w: 2, h: 1, minW: 1, maxW: 4 },
  { i: "ind-maps",        x: 10, y: 0, w: 2, h: 1, minW: 1, maxW: 4 },

  // Row 1: Alert KPIs — 4 items × 3 cols = 12 (full row)
  { i: "total-alerts", x: 0, y: 1, w: 3, h: 1, minW: 2, maxW: 6 },
  { i: "mttd",         x: 3, y: 1, w: 3, h: 1, minW: 2, maxW: 6 },
  { i: "mtta",         x: 6, y: 1, w: 3, h: 1, minW: 2, maxW: 6 },
  { i: "mttt",         x: 9, y: 1, w: 3, h: 1, minW: 2, maxW: 6 },

  // Row 2: More KPIs — MTTC + Ops KPIs — 4 items × 3 cols = 12 (full row)
  { i: "mttc",      x: 0, y: 2, w: 3, h: 1, minW: 2, maxW: 6 },
  { i: "wf-exec",   x: 3, y: 2, w: 3, h: 1, minW: 2, maxW: 6 },
  { i: "time-saved", x: 6, y: 2, w: 3, h: 1, minW: 2, maxW: 6 },
  { i: "fp-rate",   x: 9, y: 2, w: 3, h: 1, minW: 2, maxW: 6 },

  // Row 3: Remaining Ops KPIs — 4 items × 3 cols = 12 (full row)
  { i: "enrich-cov",        x: 0, y: 3, w: 3, h: 1, minW: 2, maxW: 6 },
  { i: "pending-approvals", x: 3, y: 3, w: 3, h: 1, minW: 2, maxW: 6 },
  { i: "queue-pending",     x: 6, y: 3, w: 3, h: 1, minW: 2, maxW: 6 },
  { i: "queue-oldest",      x: 9, y: 3, w: 3, h: 1, minW: 2, maxW: 6 },

  // Row 4–5: Charts — 2 × 6 cols = 12 (full row)
  { i: "sev-chart",    x: 0, y: 4, w: 6, h: 3, minW: 4, maxW: 12, minH: 2 },
  { i: "status-chart", x: 6, y: 4, w: 6, h: 3, minW: 4, maxW: 12, minH: 2 },

  // Row 7–8: Charts — 2 × 6 cols = 12 (full row)
  { i: "source-chart",  x: 0, y: 7, w: 6, h: 3, minW: 4, maxW: 12, minH: 2 },
  { i: "queue-health",  x: 6, y: 7, w: 6, h: 3, minW: 4, maxW: 12, minH: 2 },

  // Row 10–11: Charts — 1 × 6 cols (provider type chart)
  { i: "provider-type-chart", x: 0, y: 10, w: 6, h: 3, minW: 4, maxW: 12, minH: 2 },

  // Row 13: Workflow & enrichment KPIs — 5 items
  { i: "wf-configured",      x: 0,    y: 13, w: 3, h: 1, minW: 2, maxW: 6 },
  { i: "wf-success-rate",    x: 3,    y: 13, w: 3, h: 1, minW: 2, maxW: 6 },
  { i: "approvals-30d",      x: 6,    y: 13, w: 2, h: 1, minW: 2, maxW: 6 },
  { i: "median-approval-time", x: 8,  y: 13, w: 2, h: 1, minW: 2, maxW: 6 },
  { i: "mtte",               x: 10,   y: 13, w: 2, h: 1, minW: 2, maxW: 6 },
];

function loadLayout(): Layout[] | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const saved: Layout[] = JSON.parse(raw);
    const defaultMap = new Map(DEFAULT_LAYOUT.map((l) => [l.i, l]));
    const savedIds = new Set(saved.map((l) => l.i));
    const reconciled = saved.filter((l) => defaultMap.has(l.i));
    for (const dl of DEFAULT_LAYOUT) {
      if (!savedIds.has(dl.i)) reconciled.push(dl);
    }
    return reconciled;
  } catch {
    return null;
  }
}

function saveLayout(layout: Layout[]) {
  try {
    const minimal = layout.map(({ i, x, y, w, h }) => ({ i, x, y, w, h }));
    localStorage.setItem(STORAGE_KEY, JSON.stringify(minimal));
  } catch {
    // silently ignore
  }
}

export function useDashboardLayout() {
  const [layout, setLayout] = useState<Layout[]>(() => {
    const saved = loadLayout();
    return saved ?? DEFAULT_LAYOUT;
  });

  const handleLayoutChange = useCallback((newLayout: Layout[]) => {
    const defaultMap = new Map(DEFAULT_LAYOUT.map((l) => [l.i, l]));
    const merged = newLayout.map((item) => {
      const defaults = defaultMap.get(item.i);
      return defaults
        ? { ...item, minW: defaults.minW, maxW: defaults.maxW, minH: defaults.minH }
        : item;
    });
    setLayout(merged);
    saveLayout(merged);
  }, []);

  const resetLayout = useCallback(() => {
    setLayout(DEFAULT_LAYOUT);
    try {
      localStorage.removeItem(STORAGE_KEY);
      // Clean up legacy keys from older versions
      localStorage.removeItem("calseta:dashboard-grid");
      localStorage.removeItem("calseta:dashboard-layout");
    } catch {
      // silently ignore
    }
  }, []);

  return { layout, handleLayoutChange, resetLayout };
}

export { DEFAULT_LAYOUT };
