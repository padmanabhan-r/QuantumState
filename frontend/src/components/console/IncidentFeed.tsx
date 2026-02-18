import { useIncidents } from "@/hooks/useIncidents";
import type { Incident } from "@/lib/api";

const STATUS_CFG: Record<string, { accent: string; glow: string; label: string }> = {
  RESOLVED:           { accent: "hsl(160 84% 39%)",  glow: "hsl(160 84% 39% / 0.12)",  label: "Resolved" },
  PARTIALLY_RESOLVED: { accent: "hsl(38 92% 50%)",   glow: "hsl(38 92% 50% / 0.12)",   label: "Partial" },
  MONITORING:         { accent: "hsl(221 83% 53%)",  glow: "hsl(221 83% 53% / 0.12)",  label: "Monitoring" },
  ESCALATE:           { accent: "hsl(0 84% 60%)",    glow: "hsl(0 84% 60% / 0.12)",    label: "Escalate" },
};

function cfg(status: string) {
  return STATUS_CFG[status] ?? STATUS_CFG.MONITORING;
}

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  return `${Math.floor(m / 60)}h ${m % 60}m ago`;
}

function IncidentCard({ incident }: { incident: Incident }) {
  const c = cfg(incident.resolution_status);
  return (
    <div
      className="relative flex flex-col gap-3 rounded-xl p-5 overflow-hidden transition-all duration-200 hover:-translate-y-1 cursor-default"
      style={{
        background: "linear-gradient(135deg, hsl(222 47% 5%), hsl(222 47% 7%))",
        border: `1px solid color-mix(in srgb, ${c.accent} 25%, transparent)`,
        boxShadow: `0 0 0 1px color-mix(in srgb, ${c.accent} 8%, transparent), 0 4px 24px ${c.glow}`,
      }}
    >
      {/* Top accent bar */}
      <div
        className="absolute top-0 left-0 right-0 h-[2px]"
        style={{ background: `linear-gradient(90deg, transparent, ${c.accent}, transparent)` }}
      />

      {/* Service + status */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-col gap-0.5">
          <span className="font-semibold text-foreground">{incident.service || "unknown-service"}</span>
          <span className="font-mono text-xs italic text-muted-foreground">
            {incident.anomaly_type?.replace(/_/g, " ")}
          </span>
        </div>
        <span
          className="shrink-0 flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide"
          style={{
            background: `color-mix(in srgb, ${c.accent} 15%, transparent)`,
            border: `1px solid color-mix(in srgb, ${c.accent} 30%, transparent)`,
            color: c.accent,
          }}
        >
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ background: c.accent, boxShadow: `0 0 6px ${c.accent}` }}
          />
          {c.label}
        </span>
      </div>

      {/* Root cause */}
      {incident.root_cause && (
        <p className="text-xs leading-relaxed text-foreground/75 border-l-2 pl-3"
          style={{ borderColor: `color-mix(in srgb, ${c.accent} 40%, transparent)` }}
        >
          {incident.root_cause.length > 160
            ? incident.root_cause.slice(0, 160) + "…"
            : incident.root_cause}
        </p>
      )}

      {/* Footer row */}
      <div className="flex justify-between items-center pt-1 border-t font-mono text-[10px]"
        style={{ borderColor: `color-mix(in srgb, ${c.accent} 15%, transparent)` }}
      >
        <span style={{ color: `color-mix(in srgb, ${c.accent} 70%, transparent)` }}>
          {incident.mttr_estimate ? `MTTR ${incident.mttr_estimate}` : ""}
        </span>
        <span className="text-muted-foreground">{timeAgo(incident["@timestamp"])}</span>
      </div>
    </div>
  );
}

export default function IncidentFeed() {
  const { data, isLoading, isError, dataUpdatedAt } = useIncidents();

  return (
    <div className="flex flex-col gap-4">
      {/* Count + refresh row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {!isLoading && !isError && (
            <span className="rounded-full bg-primary/10 border border-primary/20 px-2 py-0.5 text-[10px] font-mono text-primary">
              {data?.total ?? 0} incidents
            </span>
          )}
        </div>
        <span className="text-[10px] font-mono text-muted-foreground">
          {isLoading ? "Loading…" : isError ? "Error" : dataUpdatedAt > 0 ? `↻ ${timeAgo(new Date(dataUpdatedAt).toISOString())}` : ""}
        </span>
      </div>

      {/* Legend */}
      {!isLoading && !isError && (data?.total ?? 0) > 0 && (
        <div className="flex gap-3 flex-wrap">
          {Object.entries(STATUS_CFG).map(([, c]) => (
            <span key={c.label} className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: c.accent }} />
              {c.label}
            </span>
          ))}
        </div>
      )}

      {isLoading && (
        <div className="py-16 text-center text-sm text-muted-foreground animate-pulse">
          Scanning indices…
        </div>
      )}

      {isError && (
        <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-5 text-sm text-destructive">
          Could not reach backend. Is the API server running on :8000?
        </div>
      )}

      {!isLoading && !isError && data?.incidents.length === 0 && (
        <div className="py-16 text-center text-sm text-muted-foreground">
          No incidents found.
        </div>
      )}

      <div className="flex flex-col gap-3">
        {data?.incidents.map((inc) => (
          <IncidentCard key={inc.id} incident={inc} />
        ))}
      </div>
    </div>
  );
}
