import { useState, useRef, useEffect, useCallback } from "react";
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

// Split text into literal and {{...}} token segments
function splitTemplate(text: string): { type: "text" | "token"; value: string }[] {
  const parts: { type: "text" | "token"; value: string }[] = [];
  const regex = /(\{\{[^}]+\}\})/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: "text", value: text.slice(lastIndex, match.index) });
    }
    parts.push({ type: "token", value: match[1] });
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < text.length) {
    parts.push({ type: "text", value: text.slice(lastIndex) });
  }
  return parts;
}

/** Whether the string contains any {{...}} template tokens. */
function hasTemplateTokens(text: string): boolean {
  return /\{\{[^}]+\}\}/.test(text);
}

/**
 * Save and restore caret position in a contentEditable element.
 * Returns the character offset from the start of the element's text.
 */
function getCaretOffset(el: HTMLElement): number {
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0) return 0;
  const range = sel.getRangeAt(0).cloneRange();
  range.selectNodeContents(el);
  range.setEnd(sel.getRangeAt(0).startContainer, sel.getRangeAt(0).startOffset);
  return range.toString().length;
}

function setCaretOffset(el: HTMLElement, offset: number) {
  const sel = window.getSelection();
  if (!sel) return;

  let remaining = offset;
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null);
  let node: Node | null;

  while ((node = walker.nextNode())) {
    const textNode = node as Text;
    if (remaining <= textNode.length) {
      const range = document.createRange();
      range.setStart(textNode, remaining);
      range.collapse(true);
      sel.removeAllRanges();
      sel.addRange(range);
      return;
    }
    remaining -= textNode.length;
  }

  // If offset exceeds text length, place at end
  const range = document.createRange();
  range.selectNodeContents(el);
  range.collapse(false);
  sel.removeAllRanges();
  sel.addRange(range);
}

/**
 * Extract raw text from a contentEditable element.
 * Pill spans have a data-token attribute containing the raw {{...}} text.
 */
function extractRawText(el: HTMLElement): string {
  let result = "";
  for (const child of Array.from(el.childNodes)) {
    if (child.nodeType === Node.TEXT_NODE) {
      result += child.textContent ?? "";
    } else if (child instanceof HTMLElement) {
      const token = child.getAttribute("data-token");
      if (token) {
        result += token;
      } else {
        result += child.textContent ?? "";
      }
    }
  }
  return result;
}

/**
 * Build HTML with pill spans for {{...}} tokens.
 */
function buildInnerHTML(text: string): string {
  if (!text) return "";
  const parts = splitTemplate(text);
  return parts
    .map((p) => {
      if (p.type === "token") {
        const inner = p.value.replace(/^\{\{|\}\}$/g, "");
        // Use zero-width spaces around the pill so the cursor can be positioned next to it
        return `\u200B<span data-token="${escapeHtml(p.value)}" contenteditable="false" class="inline-flex items-center px-1 py-0 mx-0.5 rounded bg-teal/15 text-teal border border-teal/25 text-[10px] font-semibold whitespace-nowrap align-baseline leading-[18px] select-none pointer-events-none">${escapeHtml(inner)}</span>\u200B`;
      }
      return escapeHtml(p.value);
    })
    .join("");
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

export function TemplateInput({
  value,
  onChange,
  placeholder,
  className,
  variables = TEMPLATE_VARIABLES,
}: TemplateInputProps) {
  const editableRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [focused, setFocused] = useState(false);
  const [filterText, setFilterText] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [triggerStart, setTriggerStart] = useState(-1);
  // Track whether we're programmatically updating innerHTML to avoid re-render loops
  const suppressInputRef = useRef(false);

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

  useEffect(() => {
    setSelectedIndex(0);
  }, [filterText]);

  // Sync value → innerHTML when value changes externally
  useEffect(() => {
    const el = editableRef.current;
    if (!el) return;
    const currentRaw = extractRawText(el);
    if (currentRaw !== value) {
      suppressInputRef.current = true;
      const caretPos = focused ? getCaretOffset(el) : 0;
      el.innerHTML = buildInnerHTML(value);
      if (focused) {
        requestAnimationFrame(() => setCaretOffset(el, caretPos));
      }
      suppressInputRef.current = false;
    }
  }, [value, focused]);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node) &&
        editableRef.current &&
        !editableRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const insertVariable = useCallback(
    (varName: string) => {
      const el = editableRef.current;
      if (!el || triggerStart < 0) return;

      const rawText = extractRawText(el);
      const caretPos = getCaretOffset(el);
      const before = rawText.slice(0, triggerStart);
      const after = rawText.slice(caretPos);
      const insertion = `{{${varName}}}`;
      const newValue = before + insertion + after;

      onChange(newValue);
      setOpen(false);
      setTriggerStart(-1);

      // Place cursor after the inserted variable
      requestAnimationFrame(() => {
        if (!el) return;
        el.innerHTML = buildInnerHTML(newValue);
        setCaretOffset(el, before.length + insertion.length);
        el.focus();
      });
    },
    [onChange, triggerStart],
  );

  function handleInput() {
    if (suppressInputRef.current) return;
    const el = editableRef.current;
    if (!el) return;

    const rawText = extractRawText(el);
    const caretPos = getCaretOffset(el);

    // Check if we need to re-render pills (a token was completed)
    const hadTokens = hasTemplateTokens(value);
    const hasTokensNow = hasTemplateTokens(rawText);

    if (rawText !== value) {
      onChange(rawText);
    }

    // Re-render pills if token structure changed
    if (hadTokens !== hasTokensNow || (hasTokensNow && rawText !== value)) {
      suppressInputRef.current = true;
      requestAnimationFrame(() => {
        if (!el) return;
        el.innerHTML = buildInnerHTML(rawText);
        setCaretOffset(el, caretPos);
        suppressInputRef.current = false;
      });
    }

    // Check for autocomplete trigger
    const textBefore = rawText.slice(0, caretPos);
    const lastOpen = textBefore.lastIndexOf("{{");
    const lastClose = textBefore.lastIndexOf("}}");

    if (lastOpen >= 0 && lastOpen > lastClose) {
      const partial = textBefore.slice(lastOpen + 2);
      setFilterText(partial);
      setTriggerStart(lastOpen);
      setOpen(true);
    } else {
      setOpen(false);
      setTriggerStart(-1);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    // Prevent Enter from inserting newlines (single-line input)
    if (e.key === "Enter" && !open) {
      e.preventDefault();
      return;
    }

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

  // Handle paste — strip HTML formatting, keep plain text
  function handlePaste(e: React.ClipboardEvent<HTMLDivElement>) {
    e.preventDefault();
    const text = e.clipboardData.getData("text/plain");
    document.execCommand("insertText", false, text);
  }

  return (
    <div className="relative">
      <div
        ref={editableRef}
        contentEditable
        suppressContentEditableWarning
        onInput={handleInput}
        onKeyDown={handleKeyDown}
        onPaste={handlePaste}
        onFocus={() => setFocused(true)}
        onBlur={() => {
          setFocused(false);
          setTimeout(() => setOpen(false), 150);
        }}
        data-placeholder={placeholder}
        className={cn(
          "flex items-center overflow-hidden whitespace-nowrap",
          "rounded-md border px-3 font-mono text-xs",
          "outline-none focus-visible:ring-1 focus-visible:ring-ring",
          "min-h-[28px] leading-[26px]",
          // Show placeholder via CSS when empty
          "empty:before:content-[attr(data-placeholder)] empty:before:text-muted-foreground empty:before:pointer-events-none",
          className,
        )}
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
  const parts = splitTemplate(text);
  return (
    <span className="font-mono text-[11px] break-all">
      {parts.map((p, i) => {
        if (p.type === "token") {
          const inner = p.value.replace(/^\{\{|\}\}$/g, "");
          return (
            <span
              key={i}
              className="inline-flex items-center px-1 py-0 mx-0.5 rounded bg-teal/15 text-teal border border-teal/25 text-[10px] font-semibold whitespace-nowrap align-baseline leading-[18px]"
            >
              {inner}
            </span>
          );
        }
        return <span key={i}>{p.value}</span>;
      })}
    </span>
  );
}
