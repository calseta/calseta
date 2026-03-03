import * as React from "react";
import { cn } from "@/lib/utils";
import {
  useResizableColumns,
  type ColumnDef,
} from "@/hooks/use-resizable-columns";

/* ------------------------------------------------------------------ */
/*  Context — passes resize state from ResizableTable to its children */
/* ------------------------------------------------------------------ */

interface ResizableTableContextValue {
  widths: Record<string, number>;
  onResizeStart: (columnKey: string, e: React.MouseEvent) => void;
  columnKeys: string[];
}

const ResizableTableContext =
  React.createContext<ResizableTableContextValue | null>(null);

function useResizableTableContext() {
  return React.useContext(ResizableTableContext);
}

/* ------------------------------------------------------------------ */
/*  ResizableTable                                                     */
/* ------------------------------------------------------------------ */

interface ResizableTableProps extends React.ComponentProps<"table"> {
  /** Unique key used to persist column widths in localStorage */
  storageKey: string;
  /** Column definitions — order must match the <TableHead> render order */
  columns: ColumnDef[];
}

function ResizableTable({
  storageKey,
  columns,
  className,
  children,
  ...props
}: ResizableTableProps) {
  const { widths, onResizeStart } = useResizableColumns(storageKey, columns);
  const columnKeys = columns.map((c) => c.key);

  return (
    <ResizableTableContext.Provider
      value={{ widths, onResizeStart, columnKeys }}
    >
      <div
        data-slot="table-container"
        className="relative w-full overflow-x-auto"
      >
        <table
          data-slot="table"
          className={cn("w-full caption-bottom text-sm table-fixed", className)}
          {...props}
        >
          <colgroup>
            {columns.map((col) => (
              <col
                key={col.key}
                style={{ width: widths[col.key] ?? col.initialWidth ?? 150 }}
              />
            ))}
          </colgroup>
          {children}
        </table>
      </div>
    </ResizableTableContext.Provider>
  );
}

/* ------------------------------------------------------------------ */
/*  ResizableTableHead — drop-in replacement for TableHead             */
/* ------------------------------------------------------------------ */

interface ResizableTableHeadProps extends React.ComponentProps<"th"> {
  /** Must match the corresponding ColumnDef.key */
  columnKey: string;
}

function ResizableTableHead({
  columnKey,
  className,
  children,
  ...props
}: ResizableTableHeadProps) {
  const ctx = useResizableTableContext();

  return (
    <th
      data-slot="table-head"
      className={cn(
        "text-foreground h-10 px-2 text-left align-middle font-medium whitespace-nowrap [&:has([role=checkbox])]:pr-0 [&>[role=checkbox]]:translate-y-[2px] relative select-none",
        className,
      )}
      {...props}
    >
      <div className="overflow-hidden text-ellipsis">{children}</div>
      {ctx && (
        <div
          className="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-teal/40 active:bg-teal/60 transition-colors z-10"
          onMouseDown={(e) => ctx.onResizeStart(columnKey, e)}
          role="separator"
          aria-orientation="vertical"
        />
      )}
    </th>
  );
}

export { ResizableTable, ResizableTableHead };
export type { ResizableTableProps, ResizableTableHeadProps, ColumnDef };
