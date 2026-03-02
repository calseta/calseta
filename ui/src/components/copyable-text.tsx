import { useState, useCallback } from "react";
import { Copy, Check } from "lucide-react";
import { cn } from "@/lib/utils";

interface CopyableTextProps {
  /** The text to display and copy */
  text: string;
  /** Optional className for the wrapper */
  className?: string;
  /** Render in monospace font */
  mono?: boolean;
}

export function CopyableText({ text, className, mono }: CopyableTextProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [text]);

  return (
    <span
      className={cn(
        "group inline-flex items-center gap-1.5 cursor-pointer rounded px-1.5 py-0.5 -mx-1.5 transition-colors hover:bg-surface-hover",
        mono && "font-mono",
        className,
      )}
      onClick={handleCopy}
    >
      <span className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
        {copied ? (
          <Check className="h-3 w-3 text-teal" />
        ) : (
          <Copy className="h-3 w-3 text-dim" />
        )}
      </span>
      <span className="break-all">{text}</span>
    </span>
  );
}
