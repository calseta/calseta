import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  ChevronDown,
  ChevronRight,
  ArrowUp,
  ArrowDown,
  Trash2,
} from "lucide-react";
import { KeyValueEditor } from "./key-value-editor";
import { TemplateInput } from "./template-input";
import type { StepFormState, BodyMode, HttpMethod } from "./types";
import { HTTP_METHODS, METHOD_COLORS } from "./types";

interface StepCardProps {
  step: StepFormState;
  stepNumber: number;
  totalSteps: number;
  onChange: (step: StepFormState) => void;
  onRemove: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
}

export function StepCard({
  step,
  stepNumber,
  totalSteps,
  onChange,
  onRemove,
  onMoveUp,
  onMoveDown,
}: StepCardProps) {
  function update(patch: Partial<StepFormState>) {
    onChange({ ...step, ...patch });
  }

  const bodyModes: { value: BodyMode; label: string }[] = [
    { value: "none", label: "None" },
    { value: "json_body", label: "JSON" },
    { value: "form_body", label: "Form" },
  ];

  return (
    <div className="border border-border rounded-md overflow-hidden">
      {/* Header — always visible */}
      <div
        className="flex items-center gap-2 px-3 py-2 bg-surface/50 cursor-pointer select-none"
        onClick={() => update({ collapsed: !step.collapsed })}
      >
        {step.collapsed ? (
          <ChevronRight className="h-3.5 w-3.5 text-dim shrink-0" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5 text-dim shrink-0" />
        )}

        <span className="text-[11px] text-dim font-mono shrink-0">#{stepNumber}</span>

        {step.name && (
          <span className="text-xs text-foreground font-medium truncate">{step.name}</span>
        )}

        <Badge
          variant="outline"
          className={cn("text-[10px] px-1.5 py-0 h-4 font-mono shrink-0", METHOD_COLORS[step.method])}
        >
          {step.method}
        </Badge>

        <span className="text-[11px] text-dim font-mono truncate flex-1 min-w-0">
          {step.url || "no url"}
        </span>

        {step.optional && (
          <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-4 text-dim border-border shrink-0">
            optional
          </Badge>
        )}

        {/* Action buttons — stop propagation so clicks don't toggle collapse */}
        <div className="flex items-center gap-0.5 shrink-0" onClick={(e) => e.stopPropagation()}>
          <Button
            variant="ghost"
            size="sm"
            onClick={onMoveUp}
            disabled={stepNumber <= 1}
            className="h-6 w-6 p-0 text-dim hover:text-teal"
          >
            <ArrowUp className="h-3 w-3" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onMoveDown}
            disabled={stepNumber >= totalSteps}
            className="h-6 w-6 p-0 text-dim hover:text-teal"
          >
            <ArrowDown className="h-3 w-3" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onRemove}
            className="h-6 w-6 p-0 text-dim hover:text-red-threat"
          >
            <Trash2 className="h-3 w-3" />
          </Button>
        </div>
      </div>

      {/* Body — when expanded */}
      {!step.collapsed && (
        <div className="px-3 pb-3 pt-2 space-y-3 border-t border-border">
          {/* Row 1: Name + Method */}
          <div className="flex gap-2">
            <div className="flex-1">
              <Label className="text-[11px] text-dim">Name</Label>
              <Input
                value={step.name}
                onChange={(e) => update({ name: e.target.value })}
                placeholder="e.g. lookup"
                className="bg-surface border-border text-xs h-7 mt-0.5"
              />
            </div>
            <div className="w-28">
              <Label className="text-[11px] text-dim">Method</Label>
              <Select value={step.method} onValueChange={(v) => update({ method: v as HttpMethod })}>
                <SelectTrigger className="mt-0.5 h-7 bg-surface border-border text-xs" size="sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-card border-border">
                  {HTTP_METHODS.map((m) => (
                    <SelectItem key={m} value={m} className="text-xs font-mono">
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Row 2: URL */}
          <div>
            <Label className="text-[11px] text-dim">URL</Label>
            <div className="mt-0.5">
              <TemplateInput
                value={step.url}
                onChange={(url) => update({ url })}
                placeholder="https://api.example.com/v3/{{indicator.value}}"
                className="bg-surface border-border text-xs h-7"
              />
            </div>
          </div>

          {/* Headers */}
          <KeyValueEditor
            label="Headers"
            rows={step.headers}
            onChange={(headers) => update({ headers })}
            keyPlaceholder="Header name"
            valuePlaceholder="Header value"
          />

          {/* Query Params */}
          <KeyValueEditor
            label="Query Parameters"
            rows={step.queryParams}
            onChange={(queryParams) => update({ queryParams })}
            keyPlaceholder="Param name"
            valuePlaceholder="Param value"
          />

          {/* Body mode */}
          <div>
            <Label className="text-[11px] text-dim">Request Body</Label>
            <div className="flex gap-1 mt-1">
              {bodyModes.map((bm) => (
                <button
                  key={bm.value}
                  type="button"
                  onClick={() => update({ bodyMode: bm.value })}
                  className={cn(
                    "px-2 py-0.5 text-[11px] rounded border transition-colors",
                    step.bodyMode === bm.value
                      ? "border-teal/50 bg-teal/10 text-teal"
                      : "border-border text-dim hover:text-foreground",
                  )}
                >
                  {bm.label}
                </button>
              ))}
            </div>
            {step.bodyMode === "json_body" && (
              <Textarea
                value={step.jsonBody}
                onChange={(e) => update({ jsonBody: e.target.value })}
                rows={4}
                placeholder='{"key": "{{indicator.value}}"}'
                className="bg-surface border-border text-xs font-mono mt-1.5"
              />
            )}
            {step.bodyMode === "form_body" && (
              <div className="mt-1.5">
                <KeyValueEditor
                  rows={step.formBody}
                  onChange={(formBody) => update({ formBody })}
                  keyPlaceholder="Field name"
                  valuePlaceholder="Field value"
                />
              </div>
            )}
          </div>

          {/* Row 3: Timeout + Status codes */}
          <div className="grid grid-cols-3 gap-2">
            <div>
              <Label className="text-[11px] text-dim">Timeout (seconds)</Label>
              <Input
                value={step.timeoutSeconds}
                onChange={(e) => update({ timeoutSeconds: e.target.value })}
                placeholder="30"
                className="bg-surface border-border text-xs h-7 mt-0.5"
              />
            </div>
            <div>
              <Label className="text-[11px] text-dim">Expected Status</Label>
              <Input
                value={step.expectedStatus}
                onChange={(e) => update({ expectedStatus: e.target.value })}
                placeholder="200, 201"
                className="bg-surface border-border text-xs h-7 font-mono mt-0.5"
              />
            </div>
            <div>
              <Label className="text-[11px] text-dim">Not Found Status</Label>
              <Input
                value={step.notFoundStatus}
                onChange={(e) => update({ notFoundStatus: e.target.value })}
                placeholder="404"
                className="bg-surface border-border text-xs h-7 font-mono mt-0.5"
              />
            </div>
          </div>

          {/* Optional checkbox */}
          <div className="flex items-center gap-2">
            <Checkbox
              checked={step.optional}
              onCheckedChange={(checked) => update({ optional: checked === true })}
            />
            <Label className="text-xs text-dim cursor-pointer">
              Optional step (failure won't stop the pipeline)
            </Label>
          </div>
        </div>
      )}
    </div>
  );
}
