import { useState, useCallback } from "react";
import type { Layout, LayoutItem } from "react-grid-layout/legacy";
import {
  CARD_MAP,
  SIZE_TO_GRID,
  DEFAULT_CARD_IDS,
  DEFAULT_PRESET_ID,
  PRESETS,
} from "@/components/dashboard/card-registry";

// Bump version when grid columns or default card set changes.
// This discards stale layouts from localStorage automatically.
const LAYOUT_VERSION = 5;
const STORAGE_KEY = `calseta:dashboard-grid:v${LAYOUT_VERSION}`;
const CARDS_STORAGE_KEY = `calseta:dashboard-cards:v${LAYOUT_VERSION}`;
const PRESET_STORAGE_KEY = `calseta:dashboard-preset:v${LAYOUT_VERSION}`;

// ---------------------------------------------------------------------------
// Layout generation from card IDs
// ---------------------------------------------------------------------------

/** Build a LayoutItem[] for the given card IDs, arranging them in rows. */
function buildLayout(cardIds: string[]): LayoutItem[] {
  const items: LayoutItem[] = [];
  let x = 0;
  let y = 0;
  let rowMaxH = 0;

  for (const id of cardIds) {
    const def = CARD_MAP.get(id);
    const grid = def ? SIZE_TO_GRID[def.size] : SIZE_TO_GRID["small"];
    const { w, h, minW, maxW, minH } = grid;

    // Wrap to next row if this card doesn't fit
    if (x + w > 12) {
      x = 0;
      y += rowMaxH;
      rowMaxH = 0;
    }

    items.push({ i: id, x, y, w, h, minW, maxW, ...(minH ? { minH } : {}) });
    x += w;
    if (h > rowMaxH) rowMaxH = h;
  }

  return items;
}

// ---------------------------------------------------------------------------
// Persistence helpers
// ---------------------------------------------------------------------------

function loadCards(): string[] | null {
  try {
    const raw = localStorage.getItem(CARDS_STORAGE_KEY);
    if (!raw) return null;
    const parsed: string[] = JSON.parse(raw);
    if (!Array.isArray(parsed) || parsed.length === 0) return null;
    return parsed;
  } catch {
    return null;
  }
}

function saveCards(cardIds: string[]) {
  try {
    localStorage.setItem(CARDS_STORAGE_KEY, JSON.stringify(cardIds));
  } catch {
    // silently ignore
  }
}

function loadPreset(): string | null {
  try {
    return localStorage.getItem(PRESET_STORAGE_KEY);
  } catch {
    return null;
  }
}

function savePreset(presetId: string) {
  try {
    localStorage.setItem(PRESET_STORAGE_KEY, presetId);
  } catch {
    // silently ignore
  }
}

function loadLayout(): LayoutItem[] | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const saved: LayoutItem[] = JSON.parse(raw);
    if (!Array.isArray(saved) || saved.length === 0) return null;
    return saved;
  } catch {
    return null;
  }
}

function saveLayout(layout: readonly LayoutItem[]) {
  try {
    const minimal = layout.map(({ i, x, y, w, h }) => ({ i, x, y, w, h }));
    localStorage.setItem(STORAGE_KEY, JSON.stringify(minimal));
  } catch {
    // silently ignore
  }
}

function clearStorage() {
  try {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(CARDS_STORAGE_KEY);
    localStorage.removeItem(PRESET_STORAGE_KEY);
    // Clean up legacy keys
    localStorage.removeItem("calseta:dashboard-grid");
    localStorage.removeItem("calseta:dashboard-layout");
    // Clean up older versioned keys
    for (let v = 1; v <= LAYOUT_VERSION - 1; v++) {
      localStorage.removeItem(`calseta:dashboard-grid:v${v}`);
      localStorage.removeItem(`calseta:dashboard-cards:v${v}`);
      localStorage.removeItem(`calseta:dashboard-preset:v${v}`);
    }
  } catch {
    // silently ignore
  }
}

// ---------------------------------------------------------------------------
// Reconcile saved layout with current card set
// ---------------------------------------------------------------------------

function reconcileLayout(savedLayout: LayoutItem[], cardIds: string[]): LayoutItem[] {
  const cardSet = new Set(cardIds);
  const savedMap = new Map(savedLayout.map((l) => [l.i, l]));

  // Keep only cards that are in the active set, preserving saved positions
  const reconciled: LayoutItem[] = [];
  for (const id of cardIds) {
    const saved = savedMap.get(id);
    if (saved) {
      // Restore constraints from registry
      const def = CARD_MAP.get(id);
      const grid = def ? SIZE_TO_GRID[def.size] : SIZE_TO_GRID["small"];
      reconciled.push({ ...saved, minW: grid.minW, maxW: grid.maxW, ...(grid.minH ? { minH: grid.minH } : {}) });
    } else {
      // New card — give it a position from buildLayout
      const generated = buildLayout([id]);
      if (generated[0]) {
        // Place new cards at the bottom
        const maxY = reconciled.reduce((m, l) => Math.max(m, l.y + l.h), 0);
        reconciled.push({ ...generated[0], y: maxY });
      }
    }
  }

  // Remove cards not in active set
  return reconciled.filter((l) => cardSet.has(l.i));
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useDashboardLayout() {
  const [cards, setCards] = useState<string[]>(() => {
    return loadCards() ?? [...DEFAULT_CARD_IDS];
  });

  const [activePreset, setActivePreset] = useState<string>(() => {
    return loadPreset() ?? DEFAULT_PRESET_ID;
  });

  const [layout, setLayout] = useState<LayoutItem[]>(() => {
    const savedLayout = loadLayout();
    const activeCards = loadCards() ?? [...DEFAULT_CARD_IDS];
    if (savedLayout) {
      return reconcileLayout(savedLayout, activeCards);
    }
    return buildLayout(activeCards);
  });

  const handleLayoutChange = useCallback((newLayout: Layout) => {
    setLayout((prev) => {
      // Preserve constraint fields from previous state
      const prevMap = new Map(prev.map((l) => [l.i, l]));
      const merged = newLayout.map((item) => {
        const existing = prevMap.get(item.i);
        const def = CARD_MAP.get(item.i);
        const grid = def ? SIZE_TO_GRID[def.size] : SIZE_TO_GRID["small"];
        return {
          ...item,
          minW: existing?.minW ?? grid.minW,
          maxW: existing?.maxW ?? grid.maxW,
          ...(existing?.minH != null ? { minH: existing.minH } : grid.minH ? { minH: grid.minH } : {}),
        };
      });
      saveLayout(merged);
      return merged;
    });
  }, []);

  const addCard = useCallback((id: string) => {
    setCards((prev) => {
      if (prev.includes(id)) return prev;
      const next = [...prev, id];
      saveCards(next);
      // Mark as custom (no preset)
      setActivePreset("custom");
      savePreset("custom");
      return next;
    });
    setLayout((prev) => {
      if (prev.some((l) => l.i === id)) return prev;
      const def = CARD_MAP.get(id);
      const grid = def ? SIZE_TO_GRID[def.size] : SIZE_TO_GRID["small"];
      const maxY = prev.reduce((m, l) => Math.max(m, l.y + l.h), 0);
      const newItem: LayoutItem = { i: id, x: 0, y: maxY, ...grid };
      const next = [...prev, newItem];
      saveLayout(next);
      return next;
    });
  }, []);

  const removeCard = useCallback((id: string) => {
    setCards((prev) => {
      const next = prev.filter((c) => c !== id);
      saveCards(next);
      setActivePreset("custom");
      savePreset("custom");
      return next;
    });
    setLayout((prev) => {
      const next = prev.filter((l) => l.i !== id);
      saveLayout(next);
      return next;
    });
  }, []);

  const setPresetById = useCallback((presetId: string) => {
    const preset = PRESETS.find((p) => p.id === presetId);
    if (!preset) return;
    const nextCards = [...preset.cardIds];
    const nextLayout = buildLayout(nextCards);
    setCards(nextCards);
    setLayout(nextLayout);
    setActivePreset(presetId);
    saveCards(nextCards);
    saveLayout(nextLayout);
    savePreset(presetId);
  }, []);

  const resetToDefault = useCallback(() => {
    clearStorage();
    const defaultCards = [...DEFAULT_CARD_IDS];
    const defaultLayout = buildLayout(defaultCards);
    setCards(defaultCards);
    setLayout(defaultLayout);
    setActivePreset(DEFAULT_PRESET_ID);
  }, []);

  return {
    cards,
    layout,
    activePreset,
    addCard,
    removeCard,
    setPreset: setPresetById,
    resetToDefault,
    handleLayoutChange,
  };
}

export { buildLayout };
