import { useCallback, useMemo, useState } from "react";
import { usePageSize } from "./use-page-size";

export type SortOrder = "asc" | "desc";

export interface SortState {
  column: string;
  order: SortOrder;
}

export interface FilterState {
  status: string[];
  severity: string[];
  source_name: string[];
}

const EMPTY_FILTERS: FilterState = {
  status: [],
  severity: [],
  source_name: [],
};

export function useAlertTableState() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = usePageSize();
  const [sort, setSort] = useState<SortState | null>(null);
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);

  // Three-state sort cycle: desc -> asc -> clear
  const updateSort = useCallback((column: string) => {
    setSort((prev) => {
      if (!prev || prev.column !== column) return { column, order: "desc" };
      if (prev.order === "desc") return { column, order: "asc" };
      return null; // clear
    });
    setPage(1);
  }, []);

  const updateFilter = useCallback(
    (key: keyof FilterState, values: string[]) => {
      setFilters((prev) => ({ ...prev, [key]: values }));
      setPage(1);
    },
    [],
  );

  const clearAll = useCallback(() => {
    setSort(null);
    setFilters(EMPTY_FILTERS);
    setPage(1);
  }, []);

  const hasActiveFiltersOrSort = useMemo(
    () =>
      sort !== null ||
      filters.status.length > 0 ||
      filters.severity.length > 0 ||
      filters.source_name.length > 0,
    [sort, filters],
  );

  const hasActiveFilters = useMemo(
    () =>
      filters.status.length > 0 ||
      filters.severity.length > 0 ||
      filters.source_name.length > 0,
    [filters],
  );

  // Build params for useAlerts()
  const params = useMemo(() => {
    const p: Record<string, string | number | boolean | undefined> = {
      page,
      page_size: pageSize,
    };
    if (sort) {
      p.sort_by = sort.column;
      p.sort_order = sort.order;
    }
    if (filters.status.length > 0) p.status = filters.status.join(",");
    if (filters.severity.length > 0) p.severity = filters.severity.join(",");
    if (filters.source_name.length > 0) p.source_name = filters.source_name.join(",");
    return p;
  }, [page, pageSize, sort, filters]);

  const handlePageSizeChange = useCallback(
    (value: string) => {
      setPageSize(Number(value));
      setPage(1);
    },
    [setPageSize],
  );

  return {
    page,
    setPage,
    pageSize,
    handlePageSizeChange,
    sort,
    updateSort,
    filters,
    updateFilter,
    clearAll,
    hasActiveFiltersOrSort,
    hasActiveFilters,
    params,
  };
}
