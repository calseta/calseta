import { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { Code2, Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import { StepCard } from "./step-card";
import { UrlTemplatesEditor } from "./url-templates-editor";
import type { HttpConfig, StepFormState, UrlTemplateRow } from "./types";
import {
  httpConfigToFormState,
  formStateToHttpConfig,
  createEmptyStep,
} from "./types";

interface HttpConfigBuilderProps {
  value: HttpConfig;
  onChange: (config: HttpConfig) => void;
}

export function HttpConfigBuilder({ value, onChange }: HttpConfigBuilderProps) {
  const [steps, setSteps] = useState<StepFormState[]>([]);
  const [urlTemplates, setUrlTemplates] = useState<UrlTemplateRow[]>([]);
  const [rawJsonMode, setRawJsonMode] = useState(false);
  const [rawJsonText, setRawJsonText] = useState("");
  const [rawJsonError, setRawJsonError] = useState<string | null>(null);
  const initialized = useRef(false);

  // Initialize from value on mount
  useEffect(() => {
    if (!initialized.current) {
      const state = httpConfigToFormState(value);
      setSteps(state.steps);
      setUrlTemplates(state.urlTemplates);
      initialized.current = true;
    }
  }, [value]);

  // Emit changes whenever form state changes (but not on init)
  function emitChange(newSteps: StepFormState[], newTemplates: UrlTemplateRow[]) {
    onChange(formStateToHttpConfig(newSteps, newTemplates));
  }

  function updateSteps(newSteps: StepFormState[]) {
    setSteps(newSteps);
    emitChange(newSteps, urlTemplates);
  }

  function updateUrlTemplates(newTemplates: UrlTemplateRow[]) {
    setUrlTemplates(newTemplates);
    emitChange(steps, newTemplates);
  }

  function addStep() {
    const newStep = createEmptyStep();
    updateSteps([...steps, newStep]);
  }

  function removeStep(id: string) {
    updateSteps(steps.filter((s) => s.id !== id));
  }

  function updateStep(id: string, updated: StepFormState) {
    updateSteps(steps.map((s) => (s.id === id ? updated : s)));
  }

  function moveStep(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= steps.length) return;
    const newSteps = [...steps];
    [newSteps[index], newSteps[target]] = [newSteps[target], newSteps[index]];
    updateSteps(newSteps);
  }

  // --- Raw JSON toggle ---
  function enterRawMode() {
    const config = formStateToHttpConfig(steps, urlTemplates);
    setRawJsonText(JSON.stringify(config, null, 2));
    setRawJsonError(null);
    setRawJsonMode(true);
  }

  function exitRawMode() {
    try {
      const parsed = JSON.parse(rawJsonText);
      const config: HttpConfig = {
        steps: Array.isArray(parsed.steps) ? parsed.steps : [],
        url_templates_by_type: parsed.url_templates_by_type,
      };
      const state = httpConfigToFormState(config);
      setSteps(state.steps);
      setUrlTemplates(state.urlTemplates);
      setRawJsonError(null);
      setRawJsonMode(false);
      onChange(config);
    } catch (e) {
      setRawJsonError(e instanceof Error ? e.message : "Invalid JSON");
    }
  }

  if (rawJsonMode) {
    return (
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-[11px] text-dim font-medium">Raw JSON</p>
          <Button
            variant="outline"
            size="sm"
            onClick={exitRawMode}
            className="h-7 text-xs text-dim hover:text-teal"
          >
            <Code2 className="h-3 w-3 mr-1" />
            Visual Editor
          </Button>
        </div>
        <Textarea
          value={rawJsonText}
          onChange={(e) => {
            setRawJsonText(e.target.value);
            setRawJsonError(null);
          }}
          rows={16}
          className="bg-surface border-border text-sm font-mono"
        />
        {rawJsonError && (
          <p className="text-[11px] text-red-threat">{rawJsonError}</p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <p className="text-[11px] text-dim font-medium">HTTP Steps</p>
        <Button
          variant="outline"
          size="sm"
          onClick={enterRawMode}
          className="h-7 text-xs text-dim hover:text-teal"
        >
          <Code2 className="h-3 w-3 mr-1" />
          Raw JSON
        </Button>
      </div>

      {/* Steps */}
      {steps.map((step, i) => (
        <StepCard
          key={step.id}
          step={step}
          stepNumber={i + 1}
          totalSteps={steps.length}
          onChange={(updated) => updateStep(step.id, updated)}
          onRemove={() => removeStep(step.id)}
          onMoveUp={() => moveStep(i, -1)}
          onMoveDown={() => moveStep(i, 1)}
        />
      ))}

      <Button
        variant="outline"
        size="sm"
        onClick={addStep}
        className={cn(
          "text-xs border-dashed border-border text-dim hover:text-teal hover:border-teal/40 w-full",
          steps.length === 0 && "py-4",
        )}
      >
        <Plus className="h-3 w-3 mr-1" />
        Add Step
      </Button>

      {/* URL Templates */}
      <Separator className="my-2" />
      <UrlTemplatesEditor templates={urlTemplates} onChange={updateUrlTemplates} />
    </div>
  );
}
