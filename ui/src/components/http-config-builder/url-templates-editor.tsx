import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Plus, Trash2 } from "lucide-react";
import type { UrlTemplateRow } from "./types";
import { INDICATOR_TYPES, createEmptyUrlTemplate } from "./types";

interface UrlTemplatesEditorProps {
  templates: UrlTemplateRow[];
  onChange: (templates: UrlTemplateRow[]) => void;
}

export function UrlTemplatesEditor({ templates, onChange }: UrlTemplatesEditorProps) {
  function addTemplate() {
    onChange([...templates, createEmptyUrlTemplate()]);
  }

  function removeTemplate(id: string) {
    onChange(templates.filter((t) => t.id !== id));
  }

  function updateTemplate(id: string, field: "indicatorType" | "urlTemplate", val: string) {
    onChange(templates.map((t) => (t.id === id ? { ...t, [field]: val } : t)));
  }

  return (
    <div className="space-y-1.5">
      <p className="text-[11px] text-dim font-medium">URL Templates by Indicator Type</p>
      <p className="text-[11px] text-dim">
        Override the default step URL for specific indicator types.
      </p>
      {templates.map((row) => (
        <div key={row.id} className="flex items-center gap-1.5">
          <div className="w-36">
            <Select
              value={row.indicatorType}
              onValueChange={(v) => updateTemplate(row.id, "indicatorType", v)}
            >
              <SelectTrigger className="h-7 bg-surface border-border text-xs" size="sm">
                <SelectValue placeholder="Type" />
              </SelectTrigger>
              <SelectContent className="bg-card border-border">
                {INDICATOR_TYPES.map((type) => (
                  <SelectItem key={type} value={type} className="text-xs">
                    {type}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Input
            value={row.urlTemplate}
            onChange={(e) => updateTemplate(row.id, "urlTemplate", e.target.value)}
            placeholder="https://api.example.com/v3/{{value}}"
            className="bg-surface border-border text-xs h-7 font-mono flex-1"
          />
          <Button
            variant="ghost"
            size="sm"
            onClick={() => removeTemplate(row.id)}
            className="h-7 w-7 p-0 text-dim hover:text-red-threat shrink-0"
          >
            <Trash2 className="h-3 w-3" />
          </Button>
        </div>
      ))}
      <Button
        variant="outline"
        size="sm"
        onClick={addTemplate}
        className="text-xs border-dashed border-border text-dim hover:text-teal hover:border-teal/40 h-7"
      >
        <Plus className="h-3 w-3 mr-1" />
        Add Template
      </Button>
    </div>
  );
}
