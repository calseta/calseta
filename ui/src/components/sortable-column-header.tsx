import type { SortOrder } from "@/hooks/use-table-state";
import { cn } from "@/lib/utils";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";

interface SortableColumnHeaderProps {
  label: string;
  sortKey: string;
  currentSort: { column: string; order: SortOrder } | null;
  onSort: (column: string) => void;
  /** Pass filterElement to render a filter icon/popover to the right */
  filterElement?: React.ReactNode;
}

export function SortableColumnHeader({
  label,
  sortKey,
  currentSort,
  onSort,
  filterElement,
}: SortableColumnHeaderProps) {
  const isActive = currentSort?.column === sortKey;
  const order = isActive ? currentSort.order : null;

  return (
    <div className="flex items-center gap-1">
      <button
        className={cn(
          "flex items-center gap-1 transition-colors",
          isActive ? "text-teal" : "text-dim hover:text-foreground",
        )}
        onClick={() => onSort(sortKey)}
      >
        <span className="text-xs">{label}</span>
        {order === "desc" ? (
          <ArrowDown className="h-3 w-3" />
        ) : order === "asc" ? (
          <ArrowUp className="h-3 w-3" />
        ) : (
          <ArrowUpDown className="h-3 w-3 opacity-40" />
        )}
      </button>
      {filterElement}
    </div>
  );
}
