import { useState, useRef, useCallback } from "react";
import { Tag, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface InlineTagEditorProps {
  tags: string[];
  onSave: (tags: string[]) => void;
  disabled?: boolean;
}

export function InlineTagEditor({ tags, onSave, disabled }: InlineTagEditorProps) {
  const [input, setInput] = useState("");
  const [hoveredTag, setHoveredTag] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter" && input.trim()) {
        e.preventDefault();
        const newTag = input.trim();
        if (!tags.includes(newTag)) {
          onSave([...tags, newTag]);
        }
        setInput("");
      }
      if (e.key === "Backspace" && input === "" && tags.length > 0) {
        onSave(tags.slice(0, -1));
      }
    },
    [input, tags, onSave],
  );

  function handleRemove(tag: string) {
    onSave(tags.filter((t) => t !== tag));
  }

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-1.5 rounded-md border border-transparent px-1 py-1 cursor-text",
        "transition-colors hover:border-border/60 focus-within:border-border focus-within:bg-surface/40",
        disabled && "pointer-events-none opacity-50",
      )}
      onClick={() => inputRef.current?.focus()}
    >
      {tags.map((t) => (
        <span
          key={t}
          className="group/tag relative flex items-center text-[11px] text-dim bg-surface-hover rounded transition-all duration-150"
          onMouseEnter={() => setHoveredTag(t)}
          onMouseLeave={() => setHoveredTag(null)}
        >
          <span className="flex items-center gap-1 px-2 py-0.5">
            <Tag className="h-2.5 w-2.5 shrink-0" />
            {t}
          </span>
          <span
            className={cn(
              "flex items-center justify-center overflow-hidden transition-all duration-150 ease-out cursor-pointer",
              "hover:text-red-400 text-dim/60 rounded-r",
              hoveredTag === t
                ? "w-5 opacity-100 pr-1"
                : "w-0 opacity-0",
            )}
            onClick={(e) => {
              e.stopPropagation();
              handleRemove(t);
            }}
          >
            <X className="h-3 w-3 shrink-0" />
          </span>
        </span>
      ))}
      <input
        ref={inputRef}
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={tags.length === 0 ? "Add tag..." : ""}
        className="flex-1 min-w-[60px] bg-transparent text-[11px] text-foreground placeholder:text-dim/40 outline-none border-none py-0.5 px-1"
        disabled={disabled}
      />
    </div>
  );
}
