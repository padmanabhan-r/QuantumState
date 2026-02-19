import { useState, useEffect } from "react";
import { Zap, RefreshCw, CheckCircle2, Clock, AlertTriangle, Loader2 } from "lucide-react";
import { API } from "@/lib/config";
import { useCredentials } from "@/contexts/CredentialsContext";

interface RemediationAction {
  "@timestamp": string;
  incident_id: string;
  service: string;
  action: string;
  anomaly_type: string;
  confidence_score: number;
  risk_level: string;
  status: string;
  exec_id: string;
  triggered_by: string;
  executed_at?: string;
  workflow_triggered?: boolean;
}

const ACTION_CFG: Record<string, { label: string; accent: string }> = {
  rollback_deployment: { label: "Rollback",    accent: "hsl(0 84% 60%)" },
  restart_service:     { label: "Restart",     accent: "hsl(221 83% 53%)" },
  scale_cache:         { label: "Scale Cache", accent: "hsl(188 94% 43%)" },
  restart_dependency:  { label: "Restart Dep", accent: "hsl(38 92% 50%)" },
};

const STATUS_CFG: Record<string, { accent: string; label: string; pulse: boolean }> = {
  pending:   { accent: "hsl(38 92% 50%)",  label: "Pending",   pulse: true  },
  executing: { accent: "hsl(221 83% 53%)", label: "Executing", pulse: true  },
  executed:  { accent: "hsl(160 84% 39%)", label: "Executed",  pulse: false },
  completed: { accent: "hsl(160 84% 39%)", label: "Completed", pulse: false },
  failed:    { accent: "hsl(0 84% 60%)",   label: "Failed",    pulse: false },
};

function actionCfg(action: string) {
  return ACTION_CFG[action] ?? { label: action, accent: "hsl(188 94% 43%)" };
}

function statusCfg(status: string) {
  return STATUS_CFG[status] ?? STATUS_CFG.pending;
}

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  return `${Math.floor(m / 60)}h ${m % 60}m ago`;
}

function ActionCard({ action }: { action: RemediationAction }) {
  const act = actionCfg(action.action);
  const sts = statusCfg(action.status);

  return (
    <div
      className="relative flex flex-col gap-2.5 rounded-xl p-4 overflow-hidden transition-all duration-200 hover:-translate-y-0.5"
      style={{
        background: "linear-gradient(135deg, hsl(222 47% 4%), hsl(222 47% 6%))",
        border: `1px solid color-mix(in srgb, ${act.accent} 20%, transparent)`,
        boxShadow: `0 0 16px color-mix(in srgb, ${act.accent} 6%, transparent)`,
      }}
    >
      {/* Top accent bar */}
      <div
        className="absolute top-0 left-0 right-0 h-[2px]"
        style={{ background: `linear-gradient(90deg, transparent, ${act.accent}, transparent)` }}
      />

      {/* Row 1: service + status */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-sm text-foreground">{action.service}</span>
          <span
            className="rounded-md px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
            style={{
              background: `color-mix(in srgb, ${act.accent} 15%, transparent)`,
              border: `1px solid color-mix(in srgb, ${act.accent} 30%, transparent)`,
              color: act.accent,
            }}
          >
            {act.label}
          </span>
        </div>
        <span
          className="flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
          style={{
            background: `color-mix(in srgb, ${sts.accent} 12%, transparent)`,
            border: `1px solid color-mix(in srgb, ${sts.accent} 25%, transparent)`,
            color: sts.accent,
          }}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${sts.pulse ? "animate-pulse" : ""}`}
            style={{ background: sts.accent }}
          />
          {sts.label}
        </span>
      </div>

      {/* Row 2: anomaly type */}
      {action.anomaly_type && (
        <span className="font-mono text-[11px] italic text-muted-foreground">
          {action.anomaly_type.replace(/_/g, " ")}
        </span>
      )}

      {/* Row 3: meta */}
      <div className="flex items-center justify-between font-mono text-[10px] text-muted-foreground pt-1 border-t"
        style={{ borderColor: `color-mix(in srgb, ${act.accent} 12%, transparent)` }}
      >
        <div className="flex items-center gap-3">
          <span>
            conf <span style={{ color: act.accent }}>{action.confidence_score ? (action.confidence_score * 100).toFixed(0) : "—"}%</span>
          </span>
          <span>
            risk <span style={{ color: action.risk_level === "high" ? "hsl(0 84% 60%)" : action.risk_level === "medium" ? "hsl(38 92% 50%)" : "hsl(160 84% 39%)" }}>
              {action.risk_level ?? "—"}
            </span>
          </span>
          {action.workflow_triggered && (
            <span style={{ color: "hsl(160 84% 39%)" }}>workflow ✓</span>
          )}
        </div>
        <span>{timeAgo(action["@timestamp"])}</span>
      </div>
    </div>
  );
}

export default function ActionsPanel() {
  const { credHeaders } = useCredentials();
  const [actions, setActions] = useState<RemediationAction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(false);
  const [lastUpdate, setLastUpdate] = useState(0);

  async function fetchActions() {
    try {
      const res = await fetch(`${API}/actions`, { headers: credHeaders });
      if (!res.ok) throw new Error();
      const data = await res.json();
      setActions(data.actions ?? []);
      setError(false);
      setLastUpdate(Date.now());
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchActions();
    const id = setInterval(fetchActions, 10_000);
    return () => clearInterval(id);
  }, []);

  const pending  = actions.filter((a) => a.status === "pending" || a.status === "executing").length;
  const executed = actions.filter((a) => a.status === "executed" || a.status === "completed").length;

  return (
    <div className="flex flex-col gap-4">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {pending > 0 && (
            <span className="flex items-center gap-1 rounded-full bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 text-[10px] font-mono text-amber-400">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />
              {pending} active
            </span>
          )}
          {executed > 0 && (
            <span className="rounded-full bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 text-[10px] font-mono text-emerald-400">
              {executed} executed
            </span>
          )}
        </div>
        <button
          onClick={fetchActions}
          className="flex items-center gap-1 text-[10px] font-mono text-muted-foreground hover:text-foreground transition-colors"
        >
          <RefreshCw className="h-3 w-3" />
          {lastUpdate > 0 ? timeAgo(new Date(lastUpdate).toISOString()) : ""}
        </button>
      </div>

      {loading && (
        <div className="py-16 flex items-center justify-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading actions…
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
          Could not reach backend.
        </div>
      )}

      {!loading && !error && actions.length === 0 && (
        <div className="py-16 text-center">
          <Zap className="h-8 w-8 text-muted-foreground/20 mx-auto mb-3" />
          <p className="text-sm text-muted-foreground">No remediation actions yet.</p>
          <p className="text-xs text-muted-foreground/60 mt-1">
            Actions appear here when Surgeon triggers autonomous remediation.
          </p>
        </div>
      )}

      <div className="flex flex-col gap-3">
        {actions.map((action, i) => (
          <ActionCard key={action.exec_id ?? i} action={action} />
        ))}
      </div>
    </div>
  );
}
