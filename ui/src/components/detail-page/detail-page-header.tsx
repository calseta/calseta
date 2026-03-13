import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ArrowLeft, RefreshCw } from "lucide-react";

interface DetailPageHeaderProps {
  backTo: string;
  title: string;
  badges?: ReactNode;
  actions?: ReactNode;
  subtitle?: ReactNode;
  onRefresh?: () => void;
  isRefreshing?: boolean;
}

export function DetailPageHeader({
  backTo,
  title,
  badges,
  actions,
  subtitle,
  onRefresh,
  isRefreshing,
}: DetailPageHeaderProps) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3 flex-wrap">
          <Link to={backTo}>
            <ArrowLeft className="h-5 w-5 text-dim hover:text-foreground transition-colors" />
          </Link>
          {badges}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {onRefresh && (
            <Button
              variant="ghost"
              size="sm"
              onClick={onRefresh}
              disabled={isRefreshing}
              className="h-8 w-8 p-0 text-dim hover:text-teal"
            >
              <RefreshCw className={cn("h-4 w-4", isRefreshing && "animate-spin")} />
            </Button>
          )}
          {actions}
        </div>
      </div>
      <h2 className="text-xl font-heading font-extrabold tracking-tight text-foreground">
        {title}
      </h2>
      {subtitle && <div className="mt-1">{subtitle}</div>}
    </div>
  );
}
