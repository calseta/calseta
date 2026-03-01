import { AppLayout } from "@/components/layout/app-layout";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useMetricsSummary, useApprovals } from "@/hooks/use-api";
import { formatSeconds, formatPercent } from "@/lib/format";
import {
  ShieldAlert,
  Clock,
  Workflow,
  CheckCircle2,
  AlertTriangle,
  TrendingUp,
  Timer,
  Target,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

const severityColors: Record<string, string> = {
  Critical: "#EA591B",
  High: "#FFBB1A",
  Medium: "#4D7D71",
  Low: "#57635F",
  Informational: "#2a3530",
  Pending: "#1e2a25",
};

export function DashboardPage() {
  const { data: metricsResp, isLoading: metricsLoading } = useMetricsSummary();
  const { data: approvalsResp } = useApprovals("pending");

  const metrics = metricsResp?.data;
  const pendingApprovals = approvalsResp?.data?.length ?? 0;

  const severityData = metrics
    ? Object.entries(metrics.alerts.by_severity)
        .map(([name, value]) => ({ name, value }))
        .sort(
          (a, b) =>
            ["Critical", "High", "Medium", "Low", "Informational", "Pending"].indexOf(a.name) -
            ["Critical", "High", "Medium", "Low", "Informational", "Pending"].indexOf(b.name),
        )
    : [];

  if (metricsLoading) {
    return (
      <AppLayout title="Dashboard">
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Card key={i} className="bg-card border-border">
              <CardContent className="p-6">
                <Skeleton className="h-4 w-24 mb-3" />
                <Skeleton className="h-8 w-16" />
              </CardContent>
            </Card>
          ))}
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout title="Dashboard">
      <div className="space-y-6">
        {/* KPI Cards — Row 1 */}
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <KpiCard
            icon={ShieldAlert}
            label="Total Alerts"
            value={metrics?.alerts.total ?? 0}
            sub={`${metrics?.alerts.active ?? 0} active`}
          />
          <KpiCard
            icon={Clock}
            label="MTTD"
            value={formatSeconds(metrics?.alerts.mttd_seconds ?? null)}
            sub="Mean Time to Detect"
          />
          <KpiCard
            icon={Timer}
            label="MTTA"
            value={formatSeconds(metrics?.alerts.mtta_seconds ?? null)}
            sub="Mean Time to Acknowledge"
          />
          <KpiCard
            icon={Target}
            label="MTTC"
            value={formatSeconds(metrics?.alerts.mttc_seconds ?? null)}
            sub="Mean Time to Conclusion"
          />
        </div>

        {/* KPI Cards — Row 2 */}
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <KpiCard
            icon={Workflow}
            label="Workflow Executions"
            value={metrics?.workflows.executions ?? 0}
            sub={`${formatPercent(metrics?.workflows.success_rate ?? 0)} success`}
          />
          <KpiCard
            icon={TrendingUp}
            label="Time Saved"
            value={`${(metrics?.workflows.estimated_time_saved_hours ?? 0).toFixed(1)}h`}
            sub="Estimated via workflows"
          />
          <KpiCard
            icon={AlertTriangle}
            label="False Positive Rate"
            value={formatPercent(metrics?.alerts.false_positive_rate ?? 0)}
            sub="Last 30 days"
          />
          <KpiCard
            icon={CheckCircle2}
            label="Pending Approvals"
            value={pendingApprovals}
            sub={`${formatPercent(metrics?.approvals.approval_rate ?? 0)} approval rate`}
            highlight={pendingApprovals > 0}
          />
        </div>

        {/* Charts */}
        <div className="grid gap-4 lg:grid-cols-2">
          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Alerts by Severity
              </CardTitle>
            </CardHeader>
            <CardContent>
              {severityData.length > 0 ? (
                <ResponsiveContainer width="100%" height={260}>
                  <BarChart data={severityData} barSize={32}>
                    <XAxis
                      dataKey="name"
                      axisLine={false}
                      tickLine={false}
                      tick={{ fill: "#57635F", fontSize: 11 }}
                    />
                    <YAxis
                      axisLine={false}
                      tickLine={false}
                      tick={{ fill: "#57635F", fontSize: 11 }}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#0d1117",
                        border: "1px solid #1e2a25",
                        borderRadius: 8,
                        color: "#CCD0CF",
                        fontSize: 12,
                      }}
                    />
                    <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                      {severityData.map((entry) => (
                        <Cell
                          key={entry.name}
                          fill={severityColors[entry.name] ?? "#57635F"}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex h-[260px] items-center justify-center text-sm text-dim">
                  No alert data yet
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Workflow Performance
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Stat
                label="Total Configured"
                value={metrics?.workflows.total_configured ?? 0}
              />
              <Stat
                label="Executions (30d)"
                value={metrics?.workflows.executions ?? 0}
              />
              <Stat
                label="Success Rate"
                value={formatPercent(metrics?.workflows.success_rate ?? 0)}
              />
              <Stat
                label="Approvals (30d)"
                value={metrics?.approvals.approved_last_30_days ?? 0}
              />
              <Stat
                label="Median Approval Time"
                value={
                  metrics?.approvals.median_response_time_minutes != null
                    ? `${metrics.approvals.median_response_time_minutes.toFixed(1)} min`
                    : "--"
                }
              />
            </CardContent>
          </Card>
        </div>
      </div>
    </AppLayout>
  );
}

function KpiCard({
  icon: Icon,
  label,
  value,
  sub,
  highlight,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string | number;
  sub: string;
  highlight?: boolean;
}) {
  return (
    <Card className="bg-card border-border hover:border-teal/30 transition-colors">
      <CardContent className="p-5">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-teal/10">
            <Icon className="h-4.5 w-4.5 text-teal" />
          </div>
          <div className="min-w-0">
            <p className="text-xs text-muted-foreground truncate">{label}</p>
            <p
              className={`text-xl font-heading font-extrabold tracking-tight ${
                highlight ? "text-amber" : "text-foreground"
              }`}
            >
              {value}
            </p>
            <p className="text-[11px] text-dim truncate">{sub}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-sm font-medium text-foreground">{value}</span>
    </div>
  );
}
