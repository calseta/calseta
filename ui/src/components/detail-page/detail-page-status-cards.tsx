import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

interface StatusCardItem {
  label: string;
  value: ReactNode;
  icon?: LucideIcon;
}

interface DetailPageStatusCardsProps {
  items: StatusCardItem[];
}

export function DetailPageStatusCards({ items }: DetailPageStatusCardsProps) {
  const cols = items.length <= 2 ? "md:grid-cols-2" : items.length === 3 ? "md:grid-cols-3" : "md:grid-cols-4";

  return (
    <div className={`grid grid-cols-2 ${cols} gap-3`}>
      {items.map((item) => (
        <div
          key={item.label}
          className="rounded-lg border border-border surface-2 p-4"
        >
          <div className="flex items-center gap-2">
            {item.icon && <item.icon className="h-3.5 w-3.5 text-dim" />}
            <span className="text-[11px] font-medium uppercase tracking-wider text-dim">
              {item.label}
            </span>
          </div>
          <div className="mt-1.5 text-sm font-medium text-foreground">
            {item.value}
          </div>
        </div>
      ))}
    </div>
  );
}
