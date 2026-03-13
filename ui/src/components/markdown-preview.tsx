import Markdown from "react-markdown";
import { cn } from "@/lib/utils";

interface MarkdownPreviewProps {
  content: string;
  className?: string;
}

export function MarkdownPreview({ content, className }: MarkdownPreviewProps) {
  return (
    <div className={cn("markdown-preview text-sm break-words", className)}>
      <Markdown>{content}</Markdown>
    </div>
  );
}
