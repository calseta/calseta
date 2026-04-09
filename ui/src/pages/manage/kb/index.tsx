import { AppLayout } from "@/components/layout/app-layout";
import { KBSidebar } from "./sidebar";
import { FileText } from "lucide-react";

export function KBPage() {
  return (
    <AppLayout title="Knowledge Base">
      <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
        <KBSidebar />
        <div className="flex-1 flex items-center justify-center text-center p-8">
          <div className="space-y-2">
            <FileText className="h-10 w-10 text-muted-foreground/40 mx-auto" />
            <p className="text-sm text-muted-foreground">Select a page to start editing</p>
            <p className="text-xs text-muted-foreground/60">
              Use the sidebar to navigate or create a new page with the + button
            </p>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
