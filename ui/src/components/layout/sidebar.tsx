import { Link, useRouterState } from "@tanstack/react-router";
import {
  LayoutDashboard,
  ShieldAlert,
  Workflow,
  CheckCircle2,
  Key,
  BookOpen,
  Radar,
  Bot,
  FileCode2,
  LogOut,
} from "lucide-react";

const LOGO_PATH = "/logo.svg";
import { cn } from "@/lib/utils";
import { useAuth } from "@/lib/auth";
import { Separator } from "@/components/ui/separator";

const mainNav = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/alerts", icon: ShieldAlert, label: "Alerts" },
  { to: "/workflows", icon: Workflow, label: "Workflows" },
  { to: "/approvals", icon: CheckCircle2, label: "Approvals" },
];

const settingsNav = [
  { to: "/settings/detection-rules", icon: Radar, label: "Detection Rules" },
  { to: "/settings/context-docs", icon: BookOpen, label: "Context Docs" },
  { to: "/settings/sources", icon: FileCode2, label: "Sources" },
  { to: "/settings/agents", icon: Bot, label: "Agents" },
  { to: "/settings/api-keys", icon: Key, label: "API Keys" },
];

export function Sidebar() {
  const router = useRouterState();
  const pathname = router.location.pathname;
  const { logout } = useAuth();

  return (
    <aside className="flex h-screen w-60 flex-col border-r border-border bg-sidebar">
      <div className="flex h-14 items-center px-4">
        <img
          src={LOGO_PATH}
          alt="Calseta"
          className="h-7 w-auto"
          onError={(e) => {
            // Fallback if logo file not found
            (e.target as HTMLImageElement).style.display = "none";
            (e.target as HTMLImageElement).nextElementSibling?.classList.remove("hidden");
          }}
        />
        <div className="hidden items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-teal">
            <ShieldAlert className="h-4 w-4 text-white" />
          </div>
          <span className="font-heading text-lg font-extrabold tracking-tight text-foreground">
            Calseta
          </span>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-2 py-2">
        {mainNav.map((item) => {
          const active =
            item.to === "/"
              ? pathname === "/"
              : pathname.startsWith(item.to);
          return (
            <Link
              key={item.to}
              to={item.to}
              className={cn(
                "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-teal/15 text-teal-light"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}

        <Separator className="my-3 bg-border" />

        <div className="px-3 py-1.5 text-[11px] font-medium uppercase tracking-wider text-dim">
          Settings
        </div>
        {settingsNav.map((item) => {
          const active = pathname.startsWith(item.to);
          return (
            <Link
              key={item.to}
              to={item.to}
              className={cn(
                "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-teal/15 text-teal-light"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-border p-2">
        <button
          onClick={logout}
          className="flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <LogOut className="h-4 w-4" />
          Disconnect
        </button>
      </div>
    </aside>
  );
}
