import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Zap, Play, Square, Trash2, Database, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import ElasticIcon from "@/components/ElasticIcon";

const API = "/api/sim";

type IndexInfo = { exists: boolean; count: number };
type StatusData = { streaming: boolean; indices: Record<string, IndexInfo> };

async function apiFetch(path: string, method = "GET") {
  const res = await fetch(path, { method });
  return res.json();
}

const SCENARIOS = [
  { key: "memory_leak",         icon: "🧠", title: "Memory Leak",         service: "payment-service",  desc: "Memory 55%→89% over 25 min. GC overhead critical." },
  { key: "deployment_rollback", icon: "💥", title: "Deployment Rollback", service: "checkout-service", desc: "Error rate 0.4→18/min after deploy v3.5.0." },
  { key: "error_spike",         icon: "⚡", title: "Error Spike",         service: "auth-service",     desc: "Redis evicted. Errors 28/min, latency 1200ms." },
] as const;

const SHORT = (name: string) => name.replace("-quantumstate", "");

export default function SimControl() {
  const [status, setStatus]   = useState<StatusData | null>(null);
  const [busy, setBusy]       = useState<string | null>(null);
  const [toast, setToast]     = useState<{ msg: string; ok: boolean } | null>(null);

  function showToast(msg: string, ok = true) {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 3000);
  }

  async function refreshStatus() {
    try { setStatus(await apiFetch(`${API}/status`)); } catch { /* ignore */ }
  }

  useEffect(() => {
    refreshStatus();
    const id = setInterval(refreshStatus, 5000);
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
    <div className="h-screen overflow-hidden flex flex-col bg-background text-foreground">

      {/* Header */}
      <header className="shrink-0 flex h-14 items-center gap-4 border-b border-border bg-background/80 px-6 backdrop-blur-xl">
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
      <main className="flex-1 overflow-hidden p-6">
        <div className="h-full grid grid-rows-[auto_auto_auto_auto] gap-4">

          {/* Row 1 — Setup */}
          <div className="rounded-xl border border-border bg-card p-4 flex items-center gap-6">
            <div className="shrink-0">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">Setup</div>
              <p className="text-xs text-muted-foreground">Create indices + 24 h baseline data + 4 seed incidents.</p>
            </div>
            {/* Index pills */}
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
          </div>

          {/* Row 2 — Stream */}
          <div className="rounded-xl border border-border bg-card p-4 flex items-center gap-4">
            <div className="shrink-0">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">Live Streamer</div>
              <p className="text-xs text-muted-foreground">Emits metrics every 30 s across all 4 services.</p>
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
            <div className="ml-auto flex gap-2 shrink-0">
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
          </div>

          {/* Row 3 — Inject */}
          <div className="rounded-xl border border-border bg-card p-4 flex flex-col gap-3">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Inject Anomaly</div>
            <div className="grid grid-cols-3 gap-3">
              {SCENARIOS.map((s) => (
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
          </div>

          {/* Row 4 — Cleanup */}
          <div className="rounded-xl border border-border bg-card p-4 flex flex-col gap-3">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Cleanup</div>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" disabled={busy === "clear"} onClick={() => action("clear", `${API}/cleanup/clear`, "Data cleared")} className="w-40">
                {busy === "clear" ? <RefreshCw className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Trash2 className="h-3.5 w-3.5 mr-1.5" />}
                Clear Data
              </Button>
              <Button size="sm" variant="destructive" disabled={busy === "delete"} onClick={() => action("delete", `${API}/cleanup/delete-indices`, "Indices deleted")} className="w-40">
                {busy === "delete" ? <RefreshCw className="h-3.5 w-3.5 animate-spin mr-1.5" /> : <Trash2 className="h-3.5 w-3.5 mr-1.5" />}
                Delete Indices
              </Button>
            </div>
          </div>


        </div>
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
