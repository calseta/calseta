import { useState, useCallback } from "react";

const STORAGE_KEY = "calseta:page-size";
const DEFAULT_PAGE_SIZE = 25;

function loadPageSize(): number {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_PAGE_SIZE;
    const n = parseInt(raw, 10);
    return [10, 25, 50, 100, 250, 500].includes(n) ? n : DEFAULT_PAGE_SIZE;
  } catch {
    return DEFAULT_PAGE_SIZE;
  }
}

export function usePageSize() {
  const [pageSize, setPageSizeState] = useState(loadPageSize);

  const setPageSize = useCallback((size: number) => {
    setPageSizeState(size);
    try {
      localStorage.setItem(STORAGE_KEY, String(size));
    } catch {
      // ignore
    }
  }, []);

  return [pageSize, setPageSize] as const;
}
