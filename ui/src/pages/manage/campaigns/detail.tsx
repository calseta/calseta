import { useState } from "react";
import { Link, useParams } from "@tanstack/react-router";
import { toast } from "sonner";
import { AppLayout } from "@/components/layout/app-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
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
import { Progress } from "@/components/ui/progress";
import { useCampaign, useCampaignMetrics, useAddCampaignItem } from "@/hooks/use-api";
import { formatDate, relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ArrowLeft, Plus } from "lucide-react";
import type { CampaignItem } from "@/lib/types";

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

function itemTypeColor(itemType: string): string {
  switch (itemType) {
    case "alert":
      return "text-red-threat bg-red-threat/10 border-red-threat/30";
    case "issue":
      return "text-amber bg-amber/10 border-amber/30";
    case "routine":
      return "text-teal bg-teal/10 border-teal/30";
    default:
      return "text-dim bg-dim/10 border-dim/30";
  }
}

function MetricCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string | number;
  sub?: string;
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-[11px] text-dim uppercase tracking-wide mb-1">{label}</p>
        <p className="text-2xl font-semibold text-foreground tabular-nums">{value}</p>
        {sub && <p className="text-[11px] text-dim mt-0.5">{sub}</p>}
      </CardContent>
    </Card>
  );
}

function ItemRow({ item }: { item: CampaignItem }) {
  return (
    <tr className="border-b border-border last:border-0">
      <td className="py-2.5 px-3">
        <Badge variant="outline" className={cn("text-[10px]", itemTypeColor(item.item_type))}>
          {item.item_type}
        </Badge>
      </td>
      <td className="py-2.5 px-3">
        <span className="font-mono text-xs text-dim">{item.item_uuid}</span>
      </td>
      <td className="py-2.5 px-3 text-[11px] text-dim text-right">
        {relativeTime(item.created_at)}
      </td>
    </tr>
  );
}

export function CampaignDetailPage() {
  const { uuid } = useParams({ from: "/manage/campaigns/$uuid" });
  const [showAddItem, setShowAddItem] = useState(false);
  const [formItemType, setFormItemType] = useState("");
  const [formItemUuid, setFormItemUuid] = useState("");

  const { data: campaignData, isLoading: campaignLoading } = useCampaign(uuid);
  const { data: metricsData, isLoading: metricsLoading } = useCampaignMetrics(uuid);
  const addItem = useAddCampaignItem();

  const campaign = campaignData?.data;
  const metrics = metricsData?.data;

  function handleAddItem() {
    if (!formItemType) {
      toast.error("Item type is required");
      return;
    }
    if (!formItemUuid.trim()) {
      toast.error("Item UUID is required");
      return;
    }
    addItem.mutate(
      { uuid, body: { item_type: formItemType, item_uuid: formItemUuid.trim() } },
      {
        onSuccess: () => {
          toast.success("Item added");
          setShowAddItem(false);
          setFormItemType("");
          setFormItemUuid("");
        },
        onError: () => toast.error("Failed to add item"),
      },
    );
  }

  if (campaignLoading) {
    return (
      <AppLayout title="Campaign">
        <div className="space-y-4">
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-4 w-48" />
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-20" />
            ))}
          </div>
        </div>
      </AppLayout>
    );
  }

  if (!campaign) {
    return (
      <AppLayout title="Campaign">
        <div className="text-center py-20 text-sm text-dim">Campaign not found</div>
      </AppLayout>
    );
  }

  const completionPct = metrics?.completion_pct ?? 0;

  return (
    <AppLayout title={campaign.name}>
      <div className="space-y-4">
        {/* Header */}
        <div className="flex items-start gap-3">
          <Link
            to="/manage/campaigns"
            className="mt-0.5 text-dim hover:text-foreground transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-lg font-semibold text-foreground truncate">{campaign.name}</h1>
              <Badge
                variant="outline"
                className={cn("text-[10px]", campaignStatusColor(campaign.status))}
              >
                {campaign.status}
              </Badge>
            </div>
            {campaign.description && (
              <p className="text-sm text-dim mt-0.5">{campaign.description}</p>
            )}
          </div>
        </div>

        {/* Tabs */}
        <Tabs defaultValue="overview">
          <TabsList>
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="items">
              Items
              {campaign.items.length > 0 && (
                <span className="ml-1.5 text-[10px] bg-muted px-1.5 py-0.5 rounded-full">
                  {campaign.items.length}
                </span>
              )}
            </TabsTrigger>
          </TabsList>

          {/* Overview tab */}
          <TabsContent value="overview" className="mt-4 space-y-4">
            {/* Completion */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Completion</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-dim">Progress</span>
                  <span className="font-semibold text-foreground tabular-nums">
                    {completionPct.toFixed(1)}%
                  </span>
                </div>
                <Progress value={completionPct} />
              </CardContent>
            </Card>

            {/* Metric cards */}
            {metricsLoading ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-20" />
                ))}
              </div>
            ) : metrics ? (
              <>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <MetricCard label="Total Items" value={metrics.total_items} />
                  <MetricCard label="Alerts" value={metrics.alert_count} />
                  <MetricCard label="Issues" value={metrics.issue_count} />
                  <MetricCard label="Routines" value={metrics.routine_count} />
                </div>
                <div className="grid grid-cols-3 gap-4">
                  <MetricCard
                    label="Issues Done"
                    value={metrics.issues_done}
                    sub="completed"
                  />
                  <MetricCard
                    label="In Progress"
                    value={metrics.issues_in_progress}
                    sub="active"
                  />
                  <MetricCard
                    label="Backlog"
                    value={metrics.issues_backlog}
                    sub="pending"
                  />
                </div>
              </>
            ) : null}

            {/* Campaign info */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Details</CardTitle>
              </CardHeader>
              <CardContent>
                <dl className="space-y-2 text-sm">
                  {campaign.owner_operator && (
                    <div className="flex justify-between">
                      <dt className="text-dim">Owner</dt>
                      <dd className="text-foreground">{campaign.owner_operator}</dd>
                    </div>
                  )}
                  {metrics?.target_metric && (
                    <div className="flex justify-between">
                      <dt className="text-dim">Target Metric</dt>
                      <dd className="text-foreground">{metrics.target_metric}</dd>
                    </div>
                  )}
                  {metrics?.target_value && (
                    <div className="flex justify-between">
                      <dt className="text-dim">Target Value</dt>
                      <dd className="text-foreground">
                        {metrics.current_value ?? "—"} / {metrics.target_value}
                      </dd>
                    </div>
                  )}
                  {campaign.target_date && (
                    <div className="flex justify-between">
                      <dt className="text-dim">Target Date</dt>
                      <dd className="text-foreground">{formatDate(campaign.target_date)}</dd>
                    </div>
                  )}
                  <div className="flex justify-between">
                    <dt className="text-dim">Created</dt>
                    <dd className="text-foreground">{formatDate(campaign.created_at)}</dd>
                  </div>
                </dl>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Items tab */}
          <TabsContent value="items" className="mt-4 space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-sm text-dim">{campaign.items.length} item(s)</p>
              <Button size="sm" onClick={() => setShowAddItem(true)} className="h-8 gap-1">
                <Plus className="h-3.5 w-3.5" />
                Add Item
              </Button>
            </div>

            {campaign.items.length === 0 ? (
              <Card>
                <CardContent className="py-16 text-center">
                  <p className="text-sm text-dim">No items in this campaign</p>
                </CardContent>
              </Card>
            ) : (
              <Card>
                <CardContent className="p-0">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="py-2 px-3 text-left text-[11px] uppercase tracking-wide text-dim font-medium">
                          Type
                        </th>
                        <th className="py-2 px-3 text-left text-[11px] uppercase tracking-wide text-dim font-medium">
                          UUID
                        </th>
                        <th className="py-2 px-3 text-right text-[11px] uppercase tracking-wide text-dim font-medium">
                          Added
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {campaign.items.map((item) => (
                        <ItemRow key={item.uuid} item={item} />
                      ))}
                    </tbody>
                  </table>
                </CardContent>
              </Card>
            )}
          </TabsContent>
        </Tabs>
      </div>

      {/* Add Item Dialog */}
      <Dialog
        open={showAddItem}
        onOpenChange={(open) => {
          setShowAddItem(open);
          if (!open) {
            setFormItemType("");
            setFormItemUuid("");
          }
        }}
      >
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Add Item</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label>Item Type *</Label>
              <Select value={formItemType} onValueChange={setFormItemType}>
                <SelectTrigger>
                  <SelectValue placeholder="Select type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="alert">Alert</SelectItem>
                  <SelectItem value="issue">Issue</SelectItem>
                  <SelectItem value="routine">Routine</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="item-uuid">Item UUID *</Label>
              <Input
                id="item-uuid"
                placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                className="font-mono text-xs"
                value={formItemUuid}
                onChange={(e) => setFormItemUuid(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setShowAddItem(false);
                setFormItemType("");
                setFormItemUuid("");
              }}
            >
              Cancel
            </Button>
            <Button onClick={handleAddItem} disabled={addItem.isPending}>
              {addItem.isPending ? "Adding..." : "Add Item"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppLayout>
  );
}
