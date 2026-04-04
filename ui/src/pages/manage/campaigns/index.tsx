import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import { useCampaigns, useCreateCampaign } from "@/hooks/use-api";
import { formatDate, relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Plus, RefreshCw } from "lucide-react";
import type { Campaign } from "@/lib/types";

const CATEGORY_LABELS: Record<string, string> = {
  detection_improvement: "Detection Improvement",
  response_optimization: "Response Optimization",
  vulnerability_management: "Vulnerability Mgmt",
  compliance: "Compliance",
  threat_hunting: "Threat Hunting",
  custom: "Custom",
};

const CATEGORIES = Object.keys(CATEGORY_LABELS);

const STATUS_FILTERS = ["all", "planned", "active", "completed", "cancelled"] as const;
type StatusFilter = (typeof STATUS_FILTERS)[number];

function campaignStatusColor(status: string): string {
  switch (status) {
    case "active":
      return "text-teal bg-teal/10 border-teal/30";
    case "completed":
      return "text-dim bg-dim/10 border-dim/30";
    case "planned":
      return "text-amber bg-amber/10 border-amber/30";
    case "cancelled":
      return "text-red-threat bg-red-threat/10 border-red-threat/30";
    default:
      return "text-muted-foreground bg-muted/50 border-muted";
  }
}

function campaignProgressPct(campaign: Campaign): number | null {
  if (!campaign.target_value) return null;
  const current = parseFloat(campaign.current_value ?? "0");
  const target = parseFloat(campaign.target_value);
  if (isNaN(current) || isNaN(target) || target === 0) return null;
  return Math.min(100, Math.max(0, (current / target) * 100));
}

function CampaignCard({ campaign }: { campaign: Campaign }) {
  const navigate = useNavigate();
  const pct = campaignProgressPct(campaign);

  return (
    <Card
      className="cursor-pointer hover:border-teal/40 transition-colors"
      onClick={() =>
        navigate({ to: "/manage/campaigns/$uuid", params: { uuid: campaign.uuid } })
      }
    >
      <CardContent className="p-4 space-y-3">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="outline" className="text-[10px] text-dim border-dim/30">
              {CATEGORY_LABELS[campaign.category] ?? campaign.category}
            </Badge>
            <Badge
              variant="outline"
              className={cn("text-[10px]", campaignStatusColor(campaign.status))}
            >
              {campaign.status}
            </Badge>
          </div>
          <span className="text-[11px] text-dim shrink-0">
            {campaign.items.length} item{campaign.items.length !== 1 ? "s" : ""}
          </span>
        </div>

        <div>
          <p className="text-sm font-medium text-foreground leading-snug">{campaign.name}</p>
          {campaign.description && (
            <p className="text-[12px] text-dim mt-1 line-clamp-2">{campaign.description}</p>
          )}
        </div>

        {campaign.target_metric && (
          <div className="space-y-1">
            <div className="flex items-center justify-between text-[11px] text-dim">
              <span>{campaign.target_metric}</span>
              {campaign.target_value && (
                <span>
                  {campaign.current_value ?? "—"} / {campaign.target_value}
                </span>
              )}
            </div>
            {pct !== null && <Progress value={pct} />}
          </div>
        )}

        <div className="flex items-center justify-between text-[11px] text-dim">
          {campaign.target_date ? (
            <span>Due {formatDate(campaign.target_date)}</span>
          ) : (
            <span />
          )}
          <span>{relativeTime(campaign.created_at)}</span>
        </div>
      </CardContent>
    </Card>
  );
}

function CampaignCardSkeleton() {
  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <div className="flex gap-2">
          <Skeleton className="h-5 w-24" />
          <Skeleton className="h-5 w-16" />
        </div>
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-2 w-full" />
      </CardContent>
    </Card>
  );
}

export function CampaignsPage() {
  const navigate = useNavigate();
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [showNew, setShowNew] = useState(false);

  // Form state
  const [formName, setFormName] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formCategory, setFormCategory] = useState("");
  const [formTargetMetric, setFormTargetMetric] = useState("");
  const [formTargetValue, setFormTargetValue] = useState("");
  const [formTargetDate, setFormTargetDate] = useState("");

  const params: Record<string, string | number | boolean | undefined> = {
    page_size: 200,
  };
  if (statusFilter !== "all") params.status = statusFilter;

  const { data, isLoading, refetch, isFetching } = useCampaigns(params);
  const createCampaign = useCreateCampaign();

  const campaigns = data?.data ?? [];

  function handleCreate() {
    if (!formName.trim()) {
      toast.error("Name is required");
      return;
    }
    const body: Record<string, unknown> = { name: formName.trim() };
    if (formDescription.trim()) body.description = formDescription.trim();
    if (formCategory) body.category = formCategory;
    if (formTargetMetric.trim()) body.target_metric = formTargetMetric.trim();
    if (formTargetValue.trim()) body.target_value = formTargetValue.trim();
    if (formTargetDate.trim()) body.target_date = formTargetDate.trim();

    createCampaign.mutate(body, {
      onSuccess: (res) => {
        toast.success("Campaign created");
        setShowNew(false);
        resetForm();
        navigate({ to: "/manage/campaigns/$uuid", params: { uuid: res.data.uuid } });
      },
      onError: () => toast.error("Failed to create campaign"),
    });
  }

  function resetForm() {
    setFormName("");
    setFormDescription("");
    setFormCategory("");
    setFormTargetMetric("");
    setFormTargetValue("");
    setFormTargetDate("");
  }

  return (
    <AppLayout title="Campaigns">
      <div className="space-y-4">
        {/* Top bar */}
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => refetch()}
              disabled={isFetching}
              className="h-8 w-8 p-0 text-dim hover:text-teal"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
            </Button>

            {/* Status filter chips */}
            <div className="flex items-center gap-1 flex-wrap">
              {STATUS_FILTERS.map((s) => (
                <button
                  key={s}
                  onClick={() => setStatusFilter(s)}
                  className={cn(
                    "text-[11px] px-2 py-0.5 rounded border transition-colors capitalize",
                    statusFilter === s
                      ? "border-teal text-teal bg-teal/10"
                      : "border-border text-dim hover:border-teal/40 hover:text-foreground",
                  )}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          <Button size="sm" onClick={() => setShowNew(true)} className="h-8 gap-1">
            <Plus className="h-3.5 w-3.5" />
            New Campaign
          </Button>
        </div>

        {/* Grid */}
        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <CampaignCardSkeleton key={i} />
            ))}
          </div>
        ) : campaigns.length === 0 ? (
          <Card>
            <CardContent className="py-20 text-center">
              <p className="text-sm text-dim">No campaigns</p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {campaigns.map((c) => (
              <CampaignCard key={c.uuid} campaign={c} />
            ))}
          </div>
        )}
      </div>

      {/* New Campaign Dialog */}
      <Dialog
        open={showNew}
        onOpenChange={(open) => {
          setShowNew(open);
          if (!open) resetForm();
        }}
      >
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>New Campaign</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="campaign-name">Name *</Label>
              <Input
                id="campaign-name"
                placeholder="Campaign name"
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="campaign-description">Description</Label>
              <Textarea
                id="campaign-description"
                placeholder="What is this campaign about?"
                value={formDescription}
                onChange={(e) => setFormDescription(e.target.value)}
                rows={3}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Category</Label>
              <Select value={formCategory} onValueChange={setFormCategory}>
                <SelectTrigger>
                  <SelectValue placeholder="Select category" />
                </SelectTrigger>
                <SelectContent>
                  {CATEGORIES.map((cat) => (
                    <SelectItem key={cat} value={cat}>
                      {CATEGORY_LABELS[cat]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="campaign-metric">Target Metric</Label>
              <Input
                id="campaign-metric"
                placeholder="e.g. MTTD reduction (%)"
                value={formTargetMetric}
                onChange={(e) => setFormTargetMetric(e.target.value)}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="campaign-target">Target Value</Label>
                <Input
                  id="campaign-target"
                  type="number"
                  placeholder="e.g. 25"
                  value={formTargetValue}
                  onChange={(e) => setFormTargetValue(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="campaign-date">Target Date</Label>
                <Input
                  id="campaign-date"
                  type="date"
                  value={formTargetDate}
                  onChange={(e) => setFormTargetDate(e.target.value)}
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setShowNew(false);
                resetForm();
              }}
            >
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={createCampaign.isPending}>
              {createCampaign.isPending ? "Creating..." : "Create Campaign"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppLayout>
  );
}
