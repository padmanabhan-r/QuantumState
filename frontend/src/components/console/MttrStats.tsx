import { useIncidentStats } from "@/hooks/useIncidents";
import { TrendingDown, CheckCircle2, Timer, Clock4 } from "lucide-react";

function fmt(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

const STATS = (data: ReturnType<typeof useIncidentStats>["data"], isError: boolean) => {
  const automated = data?.avg_mttr_seconds ?? 0;
  const manual    = data?.manual_baseline_seconds ?? 2820;
  const reduction = automated > 0 && manual > 0 ? Math.round(((manual - automated) / manual) * 100) : 0;

  return [
    {
      icon: <Clock4 className="h-4 w-4" />,
      label: "Incidents Today",
      value: isError ? "—" : String(data?.incidents_today ?? "—"),
      accent: "hsl(221 83% 53%)",
      glow:   "hsl(221 83% 53% / 0.15)",
    },
    {
      icon: <CheckCircle2 className="h-4 w-4" />,
      label: "Resolved",
      value: isError ? "—" : String(data?.resolved_today ?? "—"),
      accent: "hsl(160 84% 39%)",
      glow:   "hsl(160 84% 39% / 0.15)",
    },
    {
      icon: <Timer className="h-4 w-4" />,
      label: "Avg MTTR",
      value: automated ? fmt(automated) : "—",
      sub: "automated",
      accent: "hsl(188 94% 43%)",
      glow:   "hsl(188 94% 43% / 0.15)",
    },
    {
      icon: <TrendingDown className="h-4 w-4" />,
      label: "Time Saved",
      value: reduction > 0 ? `${reduction}%` : "—",
      sub: "vs 47 min manual baseline",
      accent: "hsl(38 92% 50%)",
      glow:   "hsl(38 92% 50% / 0.15)",
    },
  ];
};

export default function MttrStats() {
  const { data, isError } = useIncidentStats();
  const stats = STATS(data, isError);

  return (
    <div className="grid grid-cols-4 gap-2 sm:gap-3">
      {stats.map((s) => (
        <div
          key={s.label}
          className="flex items-center gap-2 sm:gap-3 rounded-lg sm:rounded-xl px-2 sm:px-4 py-2 sm:py-3"
          style={{
            background: `color-mix(in srgb, ${s.accent} 8%, transparent)`,
            border: `1px solid color-mix(in srgb, ${s.accent} 20%, transparent)`,
            boxShadow: `0 0 16px ${s.glow}`,
          }}
        >
          <span className="hidden sm:block shrink-0" style={{ color: s.accent }}>{s.icon}</span>
          <div className="flex flex-col min-w-0">
            <span className="text-[9px] sm:text-[10px] uppercase tracking-wider text-muted-foreground truncate">{s.label}</span>
            <span className="text-base sm:text-xl font-bold leading-tight" style={{ color: s.accent }}>
              {s.value}
            </span>
            {s.sub && (
              <span className="hidden md:block text-[10px] text-muted-foreground truncate">{s.sub}</span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
