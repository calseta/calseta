import { type ReactNode, useEffect } from "react";
import { Sidebar } from "./sidebar";
import { TopBar } from "./top-bar";

export function AppLayout({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  useEffect(() => {
    document.title = `Calseta | ${title}`;
  }, [title]);

  return (
    <div className="noise-overlay flex h-screen overflow-hidden bg-background">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar title={title} />
        <main className="flex-1 overflow-auto p-6">{children}</main>
      </div>
    </div>
  );
}
