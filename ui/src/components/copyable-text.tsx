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
        "group relative inline-flex items-center cursor-pointer rounded py-0.5 transition-all hover:bg-surface-hover",
        "pl-0 pr-1.5 hover:pl-[18px]",
        mono && "font-mono",
        className,
      )}
      onClick={handleCopy}
    >
      <span className="absolute left-1 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity">
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
