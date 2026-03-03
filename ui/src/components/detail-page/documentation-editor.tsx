import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { MarkdownPreview } from "@/components/markdown-preview";
import { Save, Pencil, Eye, FileText } from "lucide-react";

interface DocumentationEditorProps {
  content: string;
  onSave: (content: string) => void;
  isSaving: boolean;
  placeholder?: string;
  rows?: number;
  title?: string;
  templateContent?: string;
}

export function DocumentationEditor({
  content,
  onSave,
  isSaving,
  placeholder = "Write documentation in markdown...",
  rows = 16,
  title = "Documentation",
  templateContent,
}: DocumentationEditorProps) {
  const [editContent, setEditContent] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  const effectiveContent = editContent ?? content;

  function handleSave() {
    onSave(effectiveContent);
    setEditing(false);
  }

  function handleCancel() {
    setEditContent(null);
    setEditing(false);
  }

  function handleEdit() {
    setEditContent(content);
    setEditing(true);
  }

  function handleUseTemplate() {
    if (!templateContent) return;
    setEditContent(templateContent);
    setEditing(true);
  }

  return (
    <Card className="bg-card border-border">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-foreground">
          {title}
        </CardTitle>
        <div className="flex gap-2">
          {editing ? (
            <>
              <Button
                size="sm"
                variant="outline"
                onClick={handleCancel}
                className="border-border text-xs"
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={handleSave}
                disabled={isSaving}
                className="bg-teal text-white hover:bg-teal-dim text-xs"
              >
                <Save className="h-3 w-3 mr-1" />
                Save
              </Button>
            </>
          ) : (
            <>
              {templateContent && !content && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleUseTemplate}
                  className="border-border text-xs"
                >
                  <FileText className="h-3 w-3 mr-1" />
                  Use Template
                </Button>
              )}
              <Button
                size="sm"
                variant="outline"
                onClick={handleEdit}
                className="border-border text-xs"
              >
                <Pencil className="h-3 w-3 mr-1" />
                Edit
              </Button>
            </>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {editing ? (
          <Tabs defaultValue="write">
            <TabsList className="bg-surface border border-border mb-3">
              <TabsTrigger
                value="write"
                className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-xs"
              >
                <Pencil className="h-3 w-3 mr-1" />
                Write
              </TabsTrigger>
              <TabsTrigger
                value="preview"
                className="data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light text-xs"
              >
                <Eye className="h-3 w-3 mr-1" />
                Preview
              </TabsTrigger>
            </TabsList>
            <TabsContent value="write">
              <Textarea
                value={effectiveContent}
                onChange={(e) => setEditContent(e.target.value)}
                rows={rows}
                className="bg-surface border-border text-sm font-mono"
                placeholder={placeholder}
              />
            </TabsContent>
            <TabsContent value="preview">
              <div className="min-h-[200px] rounded-lg border border-border bg-surface p-4">
                {effectiveContent ? (
                  <MarkdownPreview content={effectiveContent} />
                ) : (
                  <span className="text-sm text-dim">Nothing to preview</span>
                )}
              </div>
            </TabsContent>
          </Tabs>
        ) : effectiveContent ? (
          <MarkdownPreview content={effectiveContent} />
        ) : (
          <p className="text-sm text-dim py-4">
            No {title.toLowerCase()} yet. Click Edit to add some.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
