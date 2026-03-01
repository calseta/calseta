import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";

interface DetailPageHeaderProps {
  backTo: string;
  title: string;
  badges?: ReactNode;
  actions?: ReactNode;
  subtitle?: ReactNode;
}

export function DetailPageHeader({
  backTo,
  title,
  badges,
  actions,
  subtitle,
}: DetailPageHeaderProps) {
  return (
    <div className="flex items-start gap-4">
      <Link to={backTo} className="mt-1">
        <ArrowLeft className="h-5 w-5 text-dim hover:text-foreground transition-colors" />
      </Link>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-3 flex-wrap">
          {badges}
        </div>
        <h2 className="mt-2 text-xl font-heading font-extrabold tracking-tight text-foreground">
          {title}
        </h2>
        {subtitle && <div className="mt-1">{subtitle}</div>}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  );
}
