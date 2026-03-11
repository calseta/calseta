import { useEffect, useState } from "react";
import { Clock, Globe } from "lucide-react";

function formatTime(date: Date, timeZone: string) {
  return date.toLocaleTimeString("en-US", {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function getLocalTzAbbr() {
  return Intl.DateTimeFormat("en-US", { timeZoneName: "short" })
    .formatToParts(new Date())
    .find((p) => p.type === "timeZoneName")?.value ?? "Local";
}

export function ClockDisplay() {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const localTz = getLocalTzAbbr();
  const localTime = formatTime(now, Intl.DateTimeFormat().resolvedOptions().timeZone);
  const utcTime = formatTime(now, "UTC");

  return (
    <div className="flex items-center gap-3 text-xs text-muted-foreground font-mono">
      <span className="flex items-center gap-1.5" title="Local time">
        <Clock className="h-3.5 w-3.5" />
        {localTime}
        <span className="text-dim text-[10px]">{localTz}</span>
      </span>
      <span className="flex items-center gap-1.5" title="UTC time">
        <Globe className="h-3.5 w-3.5" />
        {utcTime}
        <span className="text-dim text-[10px]">UTC</span>
      </span>
    </div>
  );
}
