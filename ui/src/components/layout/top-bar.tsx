import { useHealth } from "@/hooks/use-api";
import { cn } from "@/lib/utils";

export function TopBar({ title }: { title: string }) {
  const { data: health, isError } = useHealth();
  const isHealthy = health?.status === "ok" && !isError;
  const dbOk = health?.database === "ok";
  const queueOk = health?.queue === "ok";

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-card/50 px-6">
      <h1 className="text-lg font-heading font-extrabold tracking-tight">
        {title}
      </h1>
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <div
            className={cn(
              "h-2 w-2 rounded-full",
              isHealthy ? "bg-teal animate-pulse" : "bg-red-threat",
            )}
          />
          {isHealthy ? "Healthy" : "Degraded"}
        </div>
        {health && (
          <div className="flex gap-2 text-[11px] text-dim">
            <span className={dbOk ? "text-teal" : "text-red-threat"}>
              DB {dbOk ? "OK" : "DOWN"}
            </span>
            <span className={queueOk ? "text-teal" : "text-red-threat"}>
              Queue {queueOk ? "OK" : "DOWN"}
            </span>
            <span>v{health.version}</span>
          </div>
        )}
      </div>
    </header>
  );
}
