import { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Zap, Play, Square, Trash2, Database, RefreshCw, FlaskConical, Bot } from "lucide-react";
import { Button } from "@/components/ui/button";
import ElasticIcon from "@/components/ElasticIcon";
import { API as API_BASE } from "@/lib/config";

const API = `${API_BASE}/sim`;

type IndexInfo = { exists: boolean; count: number };
type StatusData = { streaming: boolean; indices: Record<string, IndexInfo> };
type McpAction  = { service: string; action: string; status: string; exec_id?: string; executed_at?: string };
type McpStatus  = { pending: number; recent: McpAction[] };

async function apiFetch(path: string, method = "GET") {
  const res = await fetch(path, { method });
  return res.json();
}

const SYNTH_SCENARIOS = [
  { key: "memory_leak",  icon: "🧠", title: "Memory Leak",  service: "payment-service", desc: "Memory 55%→89% over 25 min. GC overhead critical." },
  { key: "error_spike",  icon: "⚡", title: "Error Spike",  service: "auth-service",    desc: "Unhandled exception. Errors 28/min, latency 1200ms." },
] as const;

const SHORT = (name: string) => name.replace("-quantumstate", "");

export default function SimControl() {
  const [status, setStatus]       = useState<StatusData | null>(null);
  const [busy, setBusy]           = useState<string | null>(null);
  const [toast, setToast]         = useState<{ msg: string; ok: boolean } | null>(null);
  const [mcpStatus, setMcpStatus] = useState<McpStatus>({ pending: 0, recent: [] });
  const [mcpAuto, setMcpAuto]     = useState(false);
  const [mcpLast, setMcpLast]     = useState<McpAction | null>(null);
  const mcpAutoRef                = useRef(false);

  function showToast(msg: string, ok = true) {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 3000);
  }

  async function refreshStatus() {
    try { setStatus(await apiFetch(`${API}/status`)); } catch { /* ignore */ }
  }

  async function refreshMcpStatus() {
    try { setMcpStatus(await apiFetch(`${API}/mcp-runner/status`)); } catch { /* ignore */ }
  }

  async function runMcpOnce() {
    setBusy("mcp-run");
    try {
      const res = await apiFetch(`${API}/mcp-runner/execute`, "POST");
      if (res.executed) {
        setMcpLast(res.executed);
        showToast(`↺ ${res.executed.service} — ${res.executed.action}`);
      } else {
        showToast("No pending actions", true);
      }
      await refreshMcpStatus();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "MCP error", false);
    } finally {
      setBusy(null);
    }
  }

  // Auto-run loop
  useEffect(() => {
    mcpAutoRef.current = mcpAuto;
  }, [mcpAuto]);

  useEffect(() => {
    const id = setInterval(async () => {
      if (!mcpAutoRef.current) return;
      try {
        const res = await apiFetch(`${API}/mcp-runner/execute`, "POST");
        if (res.executed) setMcpLast(res.executed);
        await refreshMcpStatus();
      } catch { /* ignore */ }
    }, 3000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    refreshStatus();
    refreshMcpStatus();
    const id = setInterval(() => { refreshStatus(); refreshMcpStatus(); }, 5000);
    return () => clearInterval(id);
  }, []);

  async function action(key: string, path: string, label: string) {
    setBusy(key);
    try {
      const res = await apiFetch(path, "POST");
      if (res.ok === false && res.error) throw new Error(res.error);
      showToast(label);
      await refreshStatus();
    } catch (e) {
      showToast(e instanceof Error ? e.message : "Error", false);
    } finally {
      setBusy(null);
    }
  }

  const streaming = status?.streaming ?? false;

  return (
    <div className="h-screen overflow-auto flex flex-col bg-background text-foreground">

      {/* Header */}
      <header className="shrink-0 flex h-14 items-center gap-4 border-b border-border bg-background/80 px-6 backdrop-blur-xl sticky top-0 z-10">
        <Link to="/" className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
          <ArrowLeft className="h-4 w-4" /> Home
        </Link>
        <div className="mx-2 h-4 w-px bg-border" />
        <div className="flex items-center gap-1.5">
          <Zap className="h-4 w-4 text-secondary fill-secondary" />
          <span className="text-gradient-blue font-bold">QuantumState</span>
          <span className="rounded border border-primary/20 bg-primary/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-primary">
            Sim Control
          </span>
        </div>
        <span className="hidden md:block text-sm text-muted-foreground italic">
          Simulates a live production environment for the autonomous SRE pipeline demo
        </span>
        <div className="ml-auto font-mono text-xs flex items-center gap-1.5 text-muted-foreground">
          <ElasticIcon size={13} /> Elastic Agent Builder
        </div>
      </header>

      {/* Body */}
      <main className="flex-1 p-6 flex flex-col gap-6">

        {/* ── Baseline Setup ───────────────────────────────────────── */}
        <section className="rounded-xl border border-border bg-card p-4 flex items-center gap-6">
          <div className="shrink-0">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">Baseline Setup</div>
            <p className="text-xs text-muted-foreground">Create indices + 24 h baseline data + 4 seed incidents.</p>
          </div>
          <div className="flex gap-2 flex-1 flex-wrap">
            {status ? Object.entries(status.indices).map(([name, info]) => (
              <span
                key={name}
                className="rounded-full px-2.5 py-1 text-[10px] font-mono border"
                style={info.exists ? {
                  color: "hsl(160 84% 39%)", borderColor: "hsl(160 84% 39% / 0.3)", background: "hsl(160 84% 39% / 0.06)",
                } : {
                  color: "hsl(38 92% 50%)", borderColor: "hsl(38 92% 50% / 0.3)", background: "hsl(38 92% 50% / 0.06)",
                }}
              >
                {SHORT(name)} {info.exists ? `· ${info.count.toLocaleString()}` : "· missing"}
              </span>
            )) : <span className="text-xs text-muted-foreground/40 font-mono">Loading…</span>}
          </div>
          <Button
            size="sm"
            disabled={busy === "setup"}
            onClick={() => action("setup", `${API}/setup`, "Setup complete")}
            className="shrink-0 bg-gradient-blue text-white"
          >
            {busy === "setup" ? <RefreshCw className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Database className="h-3.5 w-3.5 mr-1.5" />}
            Run Setup
          </Button>
        </section>

        {/* ── Synthetic Sim ────────────────────────────────────────── */}
        <section className="rounded-xl border bg-card flex flex-col gap-4 p-4"
          style={{ borderColor: "hsl(221 83% 53% / 0.3)", boxShadow: "0 0 20px hsl(221 83% 53% / 0.06)" }}>
          <div className="flex items-center gap-2">
            <FlaskConical className="h-4 w-4" style={{ color: "hsl(221 83% 53%)" }} />
            <span className="text-sm font-semibold" style={{ color: "hsl(221 83% 53%)" }}>Synthetic Simulation</span>
          </div>
          <p className="text-xs text-muted-foreground -mt-2">
            Writes synthetic anomaly data directly to Elasticsearch. No Docker required.
          </p>

          {/* Live Streamer */}
          <div className="rounded-lg border border-border p-3 flex items-center gap-3" style={{ background: "hsl(222 47% 3%)" }}>
            <div className="flex-1">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-0.5">Live Streamer</div>
              <p className="text-xs text-muted-foreground">Emits metrics every 30s across all 4 services.</p>
            </div>
            <span
              className="flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold border shrink-0"
              style={streaming ? {
                color: "hsl(160 84% 39%)", borderColor: "hsl(160 84% 39% / 0.3)", background: "hsl(160 84% 39% / 0.08)",
              } : {
                color: "hsl(38 92% 50%)", borderColor: "hsl(38 92% 50% / 0.3)", background: "hsl(38 92% 50% / 0.08)",
              }}
            >
              <span className="h-1.5 w-1.5 rounded-full animate-pulse" style={{ background: streaming ? "hsl(160 84% 39%)" : "hsl(38 92% 50%)" }} />
              {streaming ? "Streaming" : "Stopped"}
            </span>
            {streaming ? (
              <Button size="sm" variant="outline" disabled={busy === "stream"} onClick={() => action("stream", `${API}/stream/stop`, "Streamer stopped")}>
                <Square className="h-3.5 w-3.5 mr-1.5" /> Stop
              </Button>
            ) : (
              <Button size="sm" disabled={busy === "stream"} onClick={() => action("stream", `${API}/stream/start`, "Streamer started")} className="bg-gradient-blue text-white">
                {busy === "stream" ? <RefreshCw className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Play className="h-3.5 w-3.5 mr-1.5" />}
                Start
              </Button>
            )}
          </div>

          {/* Inject Anomaly */}
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Inject Anomaly</div>
          <div className="grid grid-cols-2 gap-3">
            {SYNTH_SCENARIOS.map((s) => (
              <div key={s.key} className="rounded-lg border border-border p-3 flex flex-col gap-2" style={{ background: "hsl(222 47% 3%)" }}>
                <div>
                  <div className="font-semibold text-sm text-foreground">{s.icon} {s.title}</div>
                  <div className="font-mono text-[10px] text-secondary mt-0.5">{s.service}</div>
                  <p className="text-[11px] text-muted-foreground mt-1.5 leading-relaxed">{s.desc}</p>
                </div>
                <Button
                  size="sm"
                  disabled={busy === `inject-${s.key}`}
                  onClick={() => action(`inject-${s.key}`, `${API}/inject/${s.key}`, `${s.title} injected`)}
                  className="bg-gradient-blue text-white w-full mt-auto"
                >
                  {busy === `inject-${s.key}` ? <RefreshCw className="h-3 w-3 animate-spin mr-1.5" /> : null}
                  Inject
                </Button>
              </div>
            ))}
          </div>

          {/* MCP Runner */}
          <div className="rounded-lg border p-3 flex flex-col gap-2"
            style={{
              background: "hsl(222 47% 3%)",
              borderColor: mcpAuto ? "hsl(160 84% 39% / 0.35)" : "hsl(var(--border))",
              transition: "border-color 0.3s",
            }}>

            {/* Main row — mirrors Live Streamer layout */}
            <div className="flex items-center gap-3">
              <div className="flex-1">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-0.5">MCP Runner</div>
                <p className="text-xs text-muted-foreground">Synthetic <code className="text-[10px] bg-muted/40 px-1 rounded">docker restart</code> — picks up pending actions and writes recovery metrics.</p>
              </div>

              {/* Pending badge */}
              <span
                className="flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold border shrink-0 tabular-nums"
                style={mcpStatus.pending > 0 ? {
                  color: "hsl(38 92% 50%)", borderColor: "hsl(38 92% 50% / 0.3)", background: "hsl(38 92% 50% / 0.08)",
                } : {
                  color: "hsl(var(--muted-foreground))", borderColor: "hsl(var(--border))", background: "hsl(var(--border) / 0.08)",
                }}
              >
                <span className="h-1.5 w-1.5 rounded-full" style={{ background: mcpStatus.pending > 0 ? "hsl(38 92% 50%)" : "hsl(var(--muted-foreground))" }} />
                {mcpStatus.pending} pending
              </span>

              {/* Run Once */}
              <Button
                size="sm"
                disabled={busy === "mcp-run" || mcpAuto}
                onClick={runMcpOnce}
                className="bg-gradient-blue text-white shrink-0"
              >
                {busy === "mcp-run" ? <RefreshCw className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Play className="h-3.5 w-3.5 mr-1.5" />}
                Run Once
              </Button>

              {/* Auto toggle switch */}
              <button
                onClick={() => setMcpAuto(v => !v)}
                className="flex items-center gap-2 shrink-0 focus:outline-none"
                aria-label="Toggle auto mode"
              >
                <span
                  className="relative inline-flex h-5 w-9 items-center rounded-full transition-colors duration-200"
                  style={{ background: mcpAuto ? "hsl(160 84% 39%)" : "hsl(var(--muted-foreground) / 0.25)" }}
                >
                  <span
                    className="inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform duration-200"
                    style={{ transform: mcpAuto ? "translateX(18px)" : "translateX(2px)" }}
                  />
                </span>
                <span className="text-xs font-medium transition-colors duration-200"
                  style={{ color: mcpAuto ? "hsl(160 84% 39%)" : "hsl(var(--muted-foreground))" }}>
                  Auto
                </span>
              </button>
            </div>

            {/* Activity feed */}
            <div className="flex flex-col gap-0.5 rounded-md overflow-hidden border border-border/50">
              {mcpStatus.recent.length === 0 ? (
                <div className="px-2.5 py-2 text-[11px] font-mono text-muted-foreground/40 italic">
                  no activity in the last 30 min
                </div>
              ) : mcpStatus.recent.map((a, i) => {
                const isPending   = a.status === "pending";
                const isExecuting = a.status === "executing";
                const isExecuted  = a.status === "executed";
                return (
                  <div key={i} className="flex items-center gap-2 px-2.5 py-1.5 text-[11px] font-mono"
                    style={{
                      background: i === 0 ? "hsl(222 47% 5%)" : "transparent",
                      borderBottom: i < mcpStatus.recent.length - 1 ? "1px solid hsl(var(--border) / 0.4)" : "none",
                    }}>
                    <span className="h-1.5 w-1.5 rounded-full shrink-0"
                      style={{
                        background: isPending ? "hsl(38 92% 50%)" : isExecuting ? "hsl(221 83% 53%)" : isExecuted ? "hsl(160 84% 39%)" : "hsl(var(--muted-foreground))",
                        animation: isPending || isExecuting ? "pulse 1.2s infinite" : "none",
                      }} />
                    <span className="text-muted-foreground/60 shrink-0">{a.service}</span>
                    <span className="text-muted-foreground/30">→</span>
                    <span className="text-muted-foreground/80 truncate">{a.action}</span>
                    <span className="ml-auto shrink-0 text-[10px]"
                      style={{ color: isPending ? "hsl(38 92% 50%)" : isExecuting ? "hsl(221 83% 53%)" : isExecuted ? "hsl(160 84% 39%)" : "hsl(var(--muted-foreground))" }}>
                      {isPending ? "● pending" : isExecuting ? "↻ executing" : "✓ executed"}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

        </section>

        {/* ── Cleanup ─────────────────────────────────────────────── */}
        <section className="rounded-xl border border-border bg-card p-4 flex flex-col gap-3">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Cleanup</div>
          <div className="flex gap-2 flex-wrap">
            <Button size="sm" variant="outline" disabled={busy === "incidents"} onClick={() => action("incidents", `${API}/cleanup/incidents`, "Incidents cleared")} className="w-44">
              {busy === "incidents" ? <RefreshCw className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Trash2 className="h-3.5 w-3.5 mr-1.5" />}
              Clear Incidents
            </Button>
            <Button size="sm" variant="outline" disabled={busy === "clear"} onClick={() => action("clear", `${API}/cleanup/clear`, "Data cleared")} className="w-40">
              {busy === "clear" ? <RefreshCw className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Trash2 className="h-3.5 w-3.5 mr-1.5" />}
              Clear Data
            </Button>
            <Button size="sm" variant="destructive" disabled={busy === "delete"} onClick={() => action("delete", `${API}/cleanup/delete-indices`, "Indices deleted")} className="w-40">
              {busy === "delete" ? <RefreshCw className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Trash2 className="h-3.5 w-3.5 mr-1.5" />}
              Delete Indices
            </Button>
          </div>
        </section>

      </main>

      {/* Toast */}
      {toast && (
        <div
          className="fixed bottom-16 left-1/2 -translate-x-1/2 z-50 whitespace-nowrap rounded-xl px-8 py-4 text-base font-semibold shadow-2xl border backdrop-blur-sm"
          style={toast.ok ? {
            background: "hsl(160 84% 39% / 0.15)", borderColor: "hsl(160 84% 39% / 0.4)", color: "hsl(160 84% 39%)",
          } : {
            background: "hsl(var(--destructive) / 0.15)", borderColor: "hsl(var(--destructive) / 0.4)", color: "hsl(var(--destructive))",
          }}
        >
          {toast.msg}
        </div>
      )}
    </div>
  );
}
