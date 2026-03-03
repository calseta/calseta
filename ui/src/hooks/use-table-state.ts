import { useCallback, useMemo, useState } from "react";
import { usePageSize } from "./use-page-size";

export type SortOrder = "asc" | "desc";

export interface SortState {
  column: string;
  order: SortOrder;
}

/**
 * Generic table state hook for sorting, filtering, and pagination.
 *
 * `F` is the shape of the filter state — a record of string arrays keyed by
 * filter name.  Example: `{ status: [], severity: [], source_name: [] }`.
 */
export function useTableState<F extends Record<string, string[]>>(
  initialFilters: F,
) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = usePageSize();
  const [sort, setSort] = useState<SortState | null>(null);
  const [filters, setFilters] = useState<F>(initialFilters);

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
    (key: keyof F & string, values: string[]) => {
      setFilters((prev) => ({ ...prev, [key]: values }));
      setPage(1);
    },
    [],
  );

  const clearAll = useCallback(() => {
    setSort(null);
    setFilters(initialFilters);
    setPage(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const hasActiveFiltersOrSort = useMemo(
    () =>
      sort !== null ||
      Object.values(filters).some((arr) => (arr as string[]).length > 0),
    [sort, filters],
  );

  const hasActiveFilters = useMemo(
    () => Object.values(filters).some((arr) => (arr as string[]).length > 0),
    [filters],
  );

  // Build params for the API query hook
  const params = useMemo(() => {
    const p: Record<string, string | number | boolean | undefined> = {
      page,
      page_size: pageSize,
    };
    if (sort) {
      p.sort_by = sort.column;
      p.sort_order = sort.order;
    }
    for (const [key, values] of Object.entries(filters)) {
      const arr = values as string[];
      if (arr.length > 0) p[key] = arr.join(",");
    }
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
