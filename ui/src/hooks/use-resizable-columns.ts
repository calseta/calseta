import { useState, useCallback, useRef, useEffect } from "react";

export interface ColumnDef {
  /** Unique key for this column */
  key: string;
  /** Initial width in pixels (default: auto) */
  initialWidth?: number;
  /** Minimum width in pixels */
  minWidth?: number;
  /** Maximum width in pixels */
  maxWidth?: number;
}

interface ResizeState {
  columnKey: string;
  startX: number;
  startWidth: number;
}

const DEFAULT_MIN_WIDTH = 60;
const DEFAULT_MAX_WIDTH = 800;

function loadWidths(storageKey: string): Record<string, number> | null {
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function saveWidths(storageKey: string, widths: Record<string, number>) {
  try {
    localStorage.setItem(storageKey, JSON.stringify(widths));
  } catch {
    // localStorage full or unavailable — silently ignore
  }
}

export function useResizableColumns(
  storageKey: string,
  columns: ColumnDef[],
) {
  const [widths, setWidths] = useState<Record<string, number>>(() => {
    const saved = loadWidths(`table-col-widths:${storageKey}`);
    const initial: Record<string, number> = {};
    for (const col of columns) {
      initial[col.key] = saved?.[col.key] ?? col.initialWidth ?? 150;
    }
    return initial;
  });

  const resizeRef = useRef<ResizeState | null>(null);

  const onResizeStart = useCallback(
    (columnKey: string, e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      const startWidth = widths[columnKey] ?? 150;
      resizeRef.current = { columnKey, startX: e.clientX, startWidth };

      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    },
    [widths],
  );

  useEffect(() => {
    function onMouseMove(e: MouseEvent) {
      const rs = resizeRef.current;
      if (!rs) return;

      const col = columns.find((c) => c.key === rs.columnKey);
      const min = col?.minWidth ?? DEFAULT_MIN_WIDTH;
      const max = col?.maxWidth ?? DEFAULT_MAX_WIDTH;
      const delta = e.clientX - rs.startX;
      const newWidth = Math.min(max, Math.max(min, rs.startWidth + delta));

      setWidths((prev) => ({ ...prev, [rs.columnKey]: newWidth }));
    }

    function onMouseUp() {
      if (!resizeRef.current) return;
      resizeRef.current = null;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";

      // Persist after drag ends
      setWidths((current) => {
        saveWidths(`table-col-widths:${storageKey}`, current);
        return current;
      });
    }

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
    return () => {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };
  }, [columns, storageKey]);

  const resetWidths = useCallback(() => {
    const initial: Record<string, number> = {};
    for (const col of columns) {
      initial[col.key] = col.initialWidth ?? 150;
    }
    setWidths(initial);
    saveWidths(`table-col-widths:${storageKey}`, initial);
  }, [columns, storageKey]);

  return { widths, onResizeStart, resetWidths };
}
