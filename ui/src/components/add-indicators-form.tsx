import { useState, useRef, useId } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAddIndicators } from "@/hooks/use-api";
import { INDICATOR_TYPES } from "@/lib/types";
import type { IndicatorType } from "@/lib/types";
import { Trash2, Plus } from "lucide-react";

interface Row {
  id: string;
  type: IndicatorType;
  value: string;
}

interface AddIndicatorsFormProps {
  alertUuid: string;
  onDone: () => void;
}

export function AddIndicatorsForm({ alertUuid, onDone }: AddIndicatorsFormProps) {
  const prefix = useId();
  const [rows, setRows] = useState<Row[]>([
    { id: `${prefix}-0`, type: "ip", value: "" },
  ]);
  const nextId = useRef(1);
  const addIndicators = useAddIndicators();

  function addRow() {
    const id = `${prefix}-${nextId.current++}`;
    setRows((prev) => [...prev, { id, type: "ip", value: "" }]);
  }

  function removeRow(id: string) {
    setRows((prev) => (prev.length <= 1 ? prev : prev.filter((r) => r.id !== id)));
  }

  function updateRow(id: string, field: "type" | "value", val: string) {
    setRows((prev) =>
      prev.map((r) => (r.id === id ? { ...r, [field]: val } : r)),
    );
  }

  const nonEmptyRows = rows.filter((r) => r.value.trim().length > 0);
  const count = nonEmptyRows.length;

  function handleSubmit() {
    if (count === 0) return;
    addIndicators.mutate(
      {
        uuid: alertUuid,
        indicators: nonEmptyRows.map((r) => ({ type: r.type, value: r.value.trim() })),
      },
      {
        onSuccess: () => {
          toast.success(`${count} indicator${count !== 1 ? "s" : ""} added`);
          onDone();
        },
        onError: () => {
          toast.error("Failed to add indicators");
        },
      },
    );
  }

  return (
    <div className="rounded-lg border border-teal/30 bg-card p-4 space-y-3">
      <div className="space-y-2">
        {rows.map((row, idx) => (
          <div key={row.id} className="flex items-center gap-2">
            <Select
              value={row.type}
              onValueChange={(v) => updateRow(row.id, "type", v)}
            >
              <SelectTrigger className="h-8 w-40 shrink-0 text-xs bg-surface border-border">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-card border-border">
                {INDICATOR_TYPES.map((t) => (
                  <SelectItem key={t} value={t} className="text-xs">
                    {t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Input
              value={row.value}
              onChange={(e) => updateRow(row.id, "value", e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  // If this is the last row, add a new one
                  if (idx === rows.length - 1) {
                    addRow();
                  }
                  // Focus next row's input on next tick
                  setTimeout(() => {
                    const inputs = document.querySelectorAll<HTMLInputElement>(
                      "[data-indicator-input]",
                    );
                    if (inputs[idx + 1]) inputs[idx + 1].focus();
                  }, 0);
                }
              }}
              data-indicator-input=""
              placeholder="Indicator value..."
              className="h-8 flex-1 text-xs font-mono bg-surface border-border placeholder:text-dim"
            />
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8 shrink-0 text-dim hover:text-red-threat"
              onClick={() => removeRow(row.id)}
              disabled={rows.length <= 1}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={addRow}
          className="h-7 text-xs text-teal hover:text-teal-light"
        >
          <Plus className="h-3.5 w-3.5 mr-1" />
          Add row
        </Button>

        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onDone}
            className="h-7 text-xs"
          >
            Cancel
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={handleSubmit}
            disabled={count === 0 || addIndicators.isPending}
            className="h-7 text-xs bg-teal text-white hover:bg-teal-dim"
          >
            {addIndicators.isPending
              ? "Adding..."
              : `Add ${count} indicator${count !== 1 ? "s" : ""}`}
          </Button>
        </div>
      </div>
    </div>
  );
}
