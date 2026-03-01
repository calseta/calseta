import { cn } from "@/lib/utils";

interface MarkdownPreviewProps {
  content: string;
  className?: string;
}

/**
 * Simple markdown preview — renders basic markdown as styled HTML.
 * Handles headings, bold, italic, code blocks, inline code, links, lists, and blockquotes.
 * No external dependency needed for this scope.
 */
export function MarkdownPreview({ content, className }: MarkdownPreviewProps) {
  const html = renderMarkdown(content);

  return (
    <div
      className={cn(
        "prose prose-invert prose-sm max-w-none",
        "prose-headings:font-heading prose-headings:font-extrabold prose-headings:tracking-tight prose-headings:text-foreground",
        "prose-h1:text-lg prose-h2:text-base prose-h3:text-sm",
        "prose-p:text-muted-foreground prose-p:leading-relaxed",
        "prose-strong:text-foreground prose-em:text-muted-foreground",
        "prose-code:text-teal-light prose-code:bg-surface-hover prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:font-mono",
        "prose-pre:bg-[#0a0e14] prose-pre:border prose-pre:border-border prose-pre:rounded-lg prose-pre:text-xs",
        "prose-a:text-teal-light prose-a:no-underline hover:prose-a:underline",
        "prose-li:text-muted-foreground prose-li:marker:text-dim",
        "prose-blockquote:border-teal/30 prose-blockquote:text-dim",
        "prose-hr:border-border",
        className,
      )}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

function renderMarkdown(md: string): string {
  let html = md;

  // Code blocks (fenced)
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_match, _lang, code) => {
    return `<pre><code>${escapeHtml(code.trim())}</code></pre>`;
  });

  // Inline code
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

  // Headings
  html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");

  // Bold and italic
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>");
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");

  // Links
  html = html.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>',
  );

  // Blockquotes
  html = html.replace(/^> (.+)$/gm, "<blockquote>$1</blockquote>");

  // Horizontal rules
  html = html.replace(/^---$/gm, "<hr />");

  // Unordered lists
  html = html.replace(/^[\-\*] (.+)$/gm, "<li>$1</li>");
  html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, "<ul>$1</ul>");

  // Ordered lists
  html = html.replace(/^\d+\. (.+)$/gm, "<li>$1</li>");

  // Paragraphs — wrap remaining bare text lines
  html = html
    .split("\n\n")
    .map((block) => {
      const trimmed = block.trim();
      if (!trimmed) return "";
      if (
        trimmed.startsWith("<h") ||
        trimmed.startsWith("<pre") ||
        trimmed.startsWith("<ul") ||
        trimmed.startsWith("<ol") ||
        trimmed.startsWith("<blockquote") ||
        trimmed.startsWith("<hr") ||
        trimmed.startsWith("<li")
      ) {
        return trimmed;
      }
      return `<p>${trimmed.replace(/\n/g, "<br />")}</p>`;
    })
    .join("\n");

  return html;
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
