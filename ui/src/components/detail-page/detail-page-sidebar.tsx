import type { ReactNode } from "react";
import { Card, CardContent } from "@/components/ui/card";

interface DetailPageSidebarProps {
  children: ReactNode;
}

export function DetailPageSidebar({ children }: DetailPageSidebarProps) {
  return (
    <Card className="bg-card border-border">
      <CardContent className="p-4 space-y-5">{children}</CardContent>
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
      <span className="text-[11px] font-medium uppercase tracking-wider text-dim">
        {title}
      </span>
      <div className="mt-2 space-y-2">{children}</div>
    </div>
  );
}
