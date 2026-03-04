import { useState, useRef, useEffect, useCallback } from "react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { TEMPLATE_VARIABLES } from "./types";

interface TemplateVariable {
  variable: string;
  description: string;
}

interface TemplateInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  variables?: TemplateVariable[];
}

export function TemplateInput({
  value,
  onChange,
  placeholder,
  className,
  variables = TEMPLATE_VARIABLES,
}: TemplateInputProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [filterText, setFilterText] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [triggerStart, setTriggerStart] = useState(-1);

  // Strip {{ }} wrapper from variable names for matching
  const variableEntries = variables.map((v) => ({
    name: v.variable.replace(/^\{\{|\}\}$/g, ""),
    label: v.variable,
    description: v.description,
  }));

  const filtered = variableEntries.filter(
    (v) =>
      v.name.toLowerCase().includes(filterText.toLowerCase()) ||
      v.description.toLowerCase().includes(filterText.toLowerCase()),
  );

  // Reset selection when filter changes
  useEffect(() => {
    setSelectedIndex(0);
  }, [filterText]);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node) &&
        inputRef.current &&
        !inputRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const insertVariable = useCallback(
    (varName: string) => {
      const input = inputRef.current;
      if (!input || triggerStart < 0) return;

      const cursorPos = input.selectionStart ?? value.length;
      const before = value.slice(0, triggerStart);
      const after = value.slice(cursorPos);
      const insertion = `{{${varName}}}`;
      const newValue = before + insertion + after;
      onChange(newValue);

      setOpen(false);
      setTriggerStart(-1);

      // Restore cursor after the inserted variable
      requestAnimationFrame(() => {
        const newPos = before.length + insertion.length;
        input.setSelectionRange(newPos, newPos);
        input.focus();
      });
    },
    [value, onChange, triggerStart],
  );

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const newValue = e.target.value;
    const cursorPos = e.target.selectionStart ?? 0;
    onChange(newValue);

    // Look backwards from cursor for an open {{ without a closing }}
    const before = newValue.slice(0, cursorPos);
    const lastOpen = before.lastIndexOf("{{");
    const lastClose = before.lastIndexOf("}}");

    if (lastOpen >= 0 && lastOpen > lastClose) {
      // We're inside an open {{ — extract filter text
      const partial = before.slice(lastOpen + 2);
      setFilterText(partial);
      setTriggerStart(lastOpen);
      setOpen(true);
    } else {
      setOpen(false);
      setTriggerStart(-1);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || filtered.length === 0) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((i) => (i + 1) % filtered.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((i) => (i - 1 + filtered.length) % filtered.length);
    } else if (e.key === "Enter" || e.key === "Tab") {
      e.preventDefault();
      insertVariable(filtered[selectedIndex].name);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div className="relative">
      <Input
        ref={inputRef}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        className={cn("font-mono", className)}
      />
      {open && filtered.length > 0 && (
        <div
          ref={dropdownRef}
          className="absolute top-full left-0 mt-1 w-full z-50 bg-card border border-border rounded-md shadow-lg max-h-48 overflow-y-auto"
        >
          {filtered.map((v, i) => (
            <button
              key={v.name}
              type="button"
              onMouseDown={(e) => {
                e.preventDefault();
                insertVariable(v.name);
              }}
              className={cn(
                "w-full px-2.5 py-1.5 text-left flex items-center gap-2 transition-colors",
                i === selectedIndex
                  ? "bg-teal/10 text-teal"
                  : "hover:bg-surface text-foreground",
              )}
            >
              <code className="text-[11px] font-mono text-teal shrink-0 bg-teal/10 px-1 rounded">
                {v.label}
              </code>
              <span className="text-[11px] text-dim truncate">{v.description}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Renders a string with {{...}} tokens replaced by styled pill elements.
 * Used in display/read-only contexts.
 */
export function TemplatePills({ text }: { text: string }) {
  const parts = text.split(/(\{\{[^}]+\}\})/g);

  return (
    <span className="font-mono text-[11px] break-all">
      {parts.map((part, i) => {
        const match = part.match(/^\{\{([^}]+)\}\}$/);
        if (match) {
          return (
            <span
              key={i}
              className="inline-flex items-center px-1.5 py-0 mx-0.5 rounded bg-teal/15 text-teal border border-teal/25 text-[10px] font-semibold whitespace-nowrap align-baseline"
            >
              {match[1]}
            </span>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </span>
  );
}
