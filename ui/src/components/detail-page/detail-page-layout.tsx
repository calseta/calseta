import type { ReactNode } from "react";

interface DetailPageLayoutProps {
  children: ReactNode;
  sidebar?: ReactNode;
}

export function DetailPageLayout({ children, sidebar }: DetailPageLayoutProps) {
  if (!sidebar) {
    return <div className="space-y-6">{children}</div>;
  }

  return (
    <div className="flex flex-col lg:flex-row gap-6">
      <div className="flex-1 min-w-0">{children}</div>
      <div className="w-full lg:w-80 shrink-0">
        <div className="lg:sticky lg:top-0">{sidebar}</div>
      </div>
    </div>
  );
}
