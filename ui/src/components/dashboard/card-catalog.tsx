import { useState, useMemo } from "react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Search, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { CARD_REGISTRY, type CardCategory, type AnyCardDefinition } from "./card-registry";

const CATEGORIES: { value: string; label: string }[] = [
  { value: "all", label: "All" },
  { value: "alerts", label: "Alerts" },
  { value: "agents", label: "Agents" },
  { value: "workflows", label: "Workflows" },
  { value: "platform", label: "Platform" },
  { value: "costs", label: "Costs" },
];

const SIZE_LABELS: Record<string, string> = {
  small: "S",
  wide: "M",
  large: "L",
};

interface CardCatalogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  activeCardIds: string[];
  onAddCard: (id: string) => void;
}

export function CardCatalog({ open, onOpenChange, activeCardIds, onAddCard }: CardCatalogProps) {
  const [search, setSearch] = useState("");
  const [tab, setTab] = useState("all");

  const activeSet = useMemo(() => new Set(activeCardIds), [activeCardIds]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim();
    return CARD_REGISTRY.filter((card) => {
      // Category filter
      if (tab !== "all" && card.category !== tab) return false;
      // Search filter
      if (q) {
        return (
          card.title.toLowerCase().includes(q) ||
          card.description.toLowerCase().includes(q) ||
          card.id.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [search, tab]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-[400px] sm:max-w-[400px] bg-[#0d1117] border-border flex flex-col p-0">
        <SheetHeader className="px-4 pt-4 pb-0">
          <SheetTitle className="text-foreground font-heading text-base">Add Cards</SheetTitle>
          <SheetDescription className="text-dim text-xs">
            Click a card to add it to your dashboard
          </SheetDescription>
        </SheetHeader>

        <div className="px-4 pt-3 pb-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-dim" />
            <Input
              placeholder="Search cards..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8 h-8 text-xs bg-[#0a0e13] border-border"
            />
          </div>
        </div>

        <div className="px-4">
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList variant="line" className="w-full justify-start gap-0 h-8">
              {CATEGORIES.map((cat) => (
                <TabsTrigger key={cat.value} value={cat.value} className="text-[11px] px-2 py-1 h-7">
                  {cat.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>

        <div className="flex-1 overflow-y-auto px-4 pb-4 pt-2 space-y-1">
          {filtered.length === 0 && (
            <p className="text-dim text-xs text-center py-8">No cards match your search</p>
          )}
          {filtered.map((card) => {
            const isAdded = activeSet.has(card.id);
            return (
              <CatalogEntry
                key={card.id}
                card={card}
                isAdded={isAdded}
                onAdd={() => {
                  if (!isAdded) onAddCard(card.id);
                }}
              />
            );
          })}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function CatalogEntry({
  card,
  isAdded,
  onAdd,
}: {
  card: AnyCardDefinition;
  isAdded: boolean;
  onAdd: () => void;
}) {
  return (
    <button
      type="button"
      disabled={isAdded}
      onClick={onAdd}
      className={cn(
        "w-full text-left rounded-lg border px-3 py-2.5 transition-colors",
        isAdded
          ? "border-border/50 bg-[#0a0e13]/50 opacity-50 cursor-default"
          : "border-border bg-[#131920] hover:border-teal/30 hover:bg-[#131920]/80 cursor-pointer",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-foreground truncate">{card.title}</span>
            {isAdded && <CheckCircle2 className="h-3.5 w-3.5 text-teal shrink-0" />}
          </div>
          <p className="text-[11px] text-dim mt-0.5 leading-relaxed">{card.description}</p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0 mt-0.5">
          <Badge
            variant="outline"
            className="text-[10px] px-1.5 py-0 h-4 border-border text-dim capitalize"
          >
            {SIZE_LABELS[card.size] ?? card.size}
          </Badge>
          <CategoryBadge category={card.category} />
        </div>
      </div>
    </button>
  );
}

function CategoryBadge({ category }: { category: CardCategory }) {
  const colors: Record<CardCategory, string> = {
    alerts: "text-amber border-amber/30",
    agents: "text-teal border-teal/30",
    workflows: "text-teal-light border-teal-light/30",
    platform: "text-dim border-dim/30",
    costs: "text-red-threat border-red-threat/30",
  };
  return (
    <Badge
      variant="outline"
      className={cn("text-[10px] px-1.5 py-0 h-4 capitalize", colors[category])}
    >
      {category}
    </Badge>
  );
}
