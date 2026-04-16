import type { ReactNode } from "react";
import { Card, CardContent } from "@/components/ui/card";

interface DetailPageSidebarProps {
  children: ReactNode;
}

export function DetailPageSidebar({ children }: DetailPageSidebarProps) {
  return (
    <Card className="bg-card border-border py-0">
      <CardContent className="p-3 space-y-2">{children}</CardContent>
    </Card>
  );
}

interface SidebarSectionProps {
  title: string;
  children: ReactNode;
}

export function SidebarSection({ title, children }: SidebarSectionProps) {
  return (
    <div>
      <span className="micro-label">
        {title}
      </span>
      <div className="mt-1.5 space-y-1">{children}</div>
    </div>
  );
}
