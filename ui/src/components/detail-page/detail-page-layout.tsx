import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface DetailPageLayoutProps {
  children: ReactNode;
  sidebar?: ReactNode;
  sidebarClassName?: string;
}

export function DetailPageLayout({ children, sidebar, sidebarClassName }: DetailPageLayoutProps) {
  if (!sidebar) {
    return <div className="space-y-6">{children}</div>;
  }

  return (
    <div className="flex flex-col lg:flex-row gap-6">
      <div className="flex-1 min-w-0">{children}</div>
      <div className={cn("w-full lg:w-80 shrink-0", sidebarClassName)}>
        <div className="lg:sticky lg:top-0">{sidebar}</div>
      </div>
    </div>
  );
}
