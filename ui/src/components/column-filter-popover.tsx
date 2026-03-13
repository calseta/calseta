import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { ListFilter } from "lucide-react";
import { useState } from "react";

interface FilterOption {
  value: string;
  label: string;
  colorClass?: string;
}

interface ColumnFilterPopoverProps {
  options: FilterOption[];
  selected: string[];
  onChange: (values: string[]) => void;
  label: string;
}

export function ColumnFilterPopover({
  options,
  selected,
  onChange,
  label,
}: ColumnFilterPopoverProps) {
  const [open, setOpen] = useState(false);
  const isActive = selected.length > 0;

  function toggle(value: string) {
    if (selected.includes(value)) {
      onChange(selected.filter((v) => v !== value));
    } else {
      onChange([...selected, value]);
    }
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          className={cn(
            "relative inline-flex items-center justify-center h-4 w-4 rounded transition-colors",
            isActive
              ? "text-teal"
              : "text-dim/50 hover:text-dim",
          )}
          aria-label={`Filter by ${label}`}
          onClick={(e) => e.stopPropagation()}
        >
          <ListFilter className="h-3 w-3" />
          {isActive && (
            <span className="absolute -top-0.5 -right-0.5 h-1.5 w-1.5 rounded-full bg-teal" />
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="w-48 p-2 bg-card border-border"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="space-y-1">
          <div className="px-1 pb-1 text-[10px] font-medium text-dim uppercase tracking-wider">
            {label}
          </div>
          {options.map((opt) => (
            <label
              key={opt.value}
              className="flex items-center gap-2 px-1 py-1 rounded hover:bg-accent/50 cursor-pointer"
            >
              <Checkbox
                checked={selected.includes(opt.value)}
                onCheckedChange={() => toggle(opt.value)}
              />
              {opt.colorClass ? (
                <Badge
                  variant="outline"
                  className={cn("text-[10px] py-0 px-1.5", opt.colorClass)}
                >
                  {opt.label}
                </Badge>
              ) : (
                <span className="text-xs text-foreground">{opt.label}</span>
              )}
            </label>
          ))}
          {isActive && (
            <div className="pt-1 border-t border-border">
              <Button
                variant="ghost"
                size="sm"
                className="h-6 w-full text-[10px] text-dim hover:text-foreground"
                onClick={() => onChange([])}
              >
                Clear
              </Button>
            </div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
