import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Plus, Trash2 } from "lucide-react";
import type { KeyValueRow } from "./types";
import { createEmptyKvRow } from "./types";

interface KeyValueEditorProps {
  label?: string;
  rows: KeyValueRow[];
  onChange: (rows: KeyValueRow[]) => void;
  keyPlaceholder?: string;
  valuePlaceholder?: string;
}

export function KeyValueEditor({
  label,
  rows,
  onChange,
  keyPlaceholder = "Key",
  valuePlaceholder = "Value",
}: KeyValueEditorProps) {
  function addRow() {
    onChange([...rows, createEmptyKvRow()]);
  }

  function removeRow(id: string) {
    onChange(rows.filter((r) => r.id !== id));
  }

  function updateRow(id: string, field: "key" | "value", val: string) {
    onChange(rows.map((r) => (r.id === id ? { ...r, [field]: val } : r)));
  }

  return (
    <div className="space-y-1.5">
      {label && <p className="text-[11px] text-dim font-medium">{label}</p>}
      {rows.map((row) => (
        <div key={row.id} className="flex items-center gap-1.5">
          <Input
            value={row.key}
            onChange={(e) => updateRow(row.id, "key", e.target.value)}
            placeholder={keyPlaceholder}
            className="bg-surface border-border text-xs h-7 font-mono flex-1"
          />
          <Input
            value={row.value}
            onChange={(e) => updateRow(row.id, "value", e.target.value)}
            placeholder={valuePlaceholder}
            className="bg-surface border-border text-xs h-7 font-mono flex-[2]"
          />
          <Button
            variant="ghost"
            size="sm"
            onClick={() => removeRow(row.id)}
            className="h-7 w-7 p-0 text-dim hover:text-red-threat shrink-0"
          >
            <Trash2 className="h-3 w-3" />
          </Button>
        </div>
      ))}
      <Button
        variant="outline"
        size="sm"
        onClick={addRow}
        className="text-xs border-dashed border-border text-dim hover:text-teal hover:border-teal/40 h-7"
      >
        <Plus className="h-3 w-3 mr-1" />
        Add
      </Button>
    </div>
  );
}
