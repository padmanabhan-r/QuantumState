import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Play, Loader2, CheckCircle2, Circle, Square, RefreshCw, Timer, Zap, ShieldCheck, AlertTriangle } from "lucide-react";

interface Block {
  agent: string;
  event: string;
  text: string;
  meta?: Record<string, unknown>;
}

const AGENTS = [
  { id: "cassandra",     label: "Cassandra",     role: "Detection",    accent: "hsl(221 83% 53%)", glow: "hsl(221 83% 53% / 0.15)" },
  { id: "archaeologist", label: "Archaeologist", role: "Investigation", accent: "hsl(188 94% 43%)", glow: "hsl(188 94% 43% / 0.15)" },
  { id: "surgeon",       label: "Surgeon",       role: "Remediation",  accent: "hsl(160 84% 39%)", glow: "hsl(160 84% 39% / 0.15)" },
  { id: "guardian",      label: "Guardian",      role: "Verification", accent: "hsl(280 84% 60%)", glow: "hsl(280 84% 60% / 0.15)" },
];

function agentCfg(id: string) {
  return AGENTS.find((a) => a.id === id) ?? AGENTS[0];
}

export default function PipelinePanel() {
  const [running, setRunning]           = useState(false);
  const [blocks, setBlocks]             = useState<Block[]>([]);
  const [currentAgent, setCurrentAgent] = useState<string | null>(null);
  const [doneAgents, setDoneAgents]     = useState<string[]>([]);
  const [done, setDone]                 = useState(false);
  const [doneMsg, setDoneMsg]           = useState("");
  const [error, setError]               = useState<string | null>(null);

  // Guardian state
  const [remediatedService, setRemediatedService] = useState<string | null>(null);
  const [guardianRunning, setGuardianRunning]     = useState(false);

  // Auto-run state
  const [mode, setMode]           = useState<"manual" | "auto">("manual");
  const [interval, setInterval_]  = useState(60);
  const [autoActive, setAutoActive] = useState(false);
  const [countdown, setCountdown]  = useState(0);

  const outputRef    = useRef<HTMLDivElement>(null);
  const autoTimer    = useRef<ReturnType<typeof setTimeout> | null>(null);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const runningRef   = useRef(false);

  // Keep runningRef in sync
  useEffect(() => { runningRef.current = running; }, [running]);

  // Cleanup on unmount
  useEffect(() => () => { stopAuto(); }, []);

  function appendBlock(b: Block) {
    setBlocks((prev) => {
      if (b.event === "message_chunk" && prev.length > 0 &&
          prev[prev.length - 1].agent === b.agent &&
          prev[prev.length - 1].event === "message_chunk") {
        const next = [...prev];
        next[next.length - 1] = { ...next[next.length - 1], text: next[next.length - 1].text + b.text };
        return next;
      }
      return [...prev, b];
    });
    setTimeout(() => {
      if (outputRef.current) outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }, 20);
  }

  async function runPipeline() {
    if (runningRef.current) return;
    setRunning(true); setDone(false); setDoneMsg(""); setError(null);
    setBlocks([]); setCurrentAgent(null); setDoneAgents([]);

    try {
      const res = await fetch("/api/pipeline/run", { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      if (!res.body) throw new Error("No response body");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done: streamDone, value } = await reader.read();
        if (streamDone) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        let evtName = "";
        for (const line of lines) {
          if (line.startsWith("event:")) { evtName = line.slice(6).trim(); }
          else if (line.startsWith("data:")) {
            try {
              const payload = JSON.parse(line.slice(5).trim());
              const agent = payload.agent ?? "system";
              const text  = payload.text  ?? "";

              if (evtName === "agent_start") {
                setCurrentAgent(agent);
                appendBlock({ agent, event: "agent_start", text: payload.label ?? agentCfg(agent).label });
              } else if (evtName === "message_chunk") {
                appendBlock({ agent, event: "message_chunk", text });
              } else if (evtName === "reasoning") {
                appendBlock({ agent, event: "reasoning", text });
              } else if (evtName === "agent_complete") {
                setDoneAgents((d) => [...d, agent]);
              } else if (evtName === "pipeline_complete") {
                setDone(true); setCurrentAgent(null); setDoneMsg(text);
              } else if (evtName === "error") {
                setError(text);
              } else if (evtName === "remediation_triggered") {
                if (payload.service) setRemediatedService(payload.service as string);
                appendBlock({ agent, event: evtName, text, meta: payload });
              } else if (
                evtName === "remediation_executing" ||
                evtName === "remediation_skipped" ||
                evtName === "remediation_error"
              ) {
                appendBlock({ agent, event: evtName, text, meta: payload });
              }
            } catch { /* ignore */ }
          }
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setRunning(false);
    }
  }

  function scheduleNext(secs: number) {
    setCountdown(secs);
    countdownRef.current = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) { clearInterval(countdownRef.current!); return 0; }
        return c - 1;
      });
    }, 1000);
    autoTimer.current = setTimeout(async () => {
      await runPipeline();
      // schedule next only if still active
      setAutoActive((active) => {
        if (active) scheduleNext(secs);
        return active;
      });
    }, secs * 1000);
  }

  function startAuto() {
    setAutoActive(true);
    runPipeline().then(() => {
      setAutoActive((active) => {
        if (active) scheduleNext(interval);
        return active;
      });
    });
  }

  function stopAuto() {
    setAutoActive(false);
    if (autoTimer.current)    { clearTimeout(autoTimer.current);   autoTimer.current = null; }
    if (countdownRef.current) { clearInterval(countdownRef.current); countdownRef.current = null; }
    setCountdown(0);
  }

  async function runGuardian(service: string) {
    if (guardianRunning) return;
    setGuardianRunning(true);
    setCurrentAgent("guardian");

    try {
      const res = await fetch(`/api/guardian/stream/${encodeURIComponent(service)}`, { method: "POST" });
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done: streamDone, value } = await reader.read();
        if (streamDone) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        let evtName = "";
        for (const line of lines) {
          if (line.startsWith("event:")) { evtName = line.slice(6).trim(); }
          else if (line.startsWith("data:")) {
            try {
              const payload = JSON.parse(line.slice(5).trim());
              const text = payload.text ?? "";
              if (evtName === "agent_start") {
                appendBlock({ agent: "guardian", event: "agent_start", text: payload.label ?? "Guardian — Verification" });
              } else if (evtName === "message_chunk") {
                appendBlock({ agent: "guardian", event: "message_chunk", text });
              } else if (evtName === "reasoning") {
                appendBlock({ agent: "guardian", event: "reasoning", text });
              } else if (evtName === "agent_complete") {
                setDoneAgents((d) => [...d, "guardian"]);
                setCurrentAgent(null);
              } else if (evtName === "guardian_verdict") {
                appendBlock({ agent: "guardian", event: "guardian_verdict", text, meta: payload });
                setRemediatedService(null);
              } else if (evtName === "error") {
                appendBlock({ agent: "guardian", event: "remediation_error", text });
              }
            } catch { /* ignore */ }
          }
        }
      }
    } catch (err) {
      appendBlock({ agent: "guardian", event: "remediation_error", text: err instanceof Error ? err.message : "Guardian failed" });
    } finally {
      setGuardianRunning(false);
      setCurrentAgent(null);
    }
  }

  const cfg = currentAgent ? agentCfg(currentAgent) : null;

  return (
    <div className="flex flex-col gap-4 h-full">

      {/* Controls card */}
      <div
        className="rounded-xl p-4 border border-border shrink-0"
        style={{ background: "linear-gradient(135deg, hsl(222 47% 4%), hsl(222 47% 6%))" }}
      >
        {/* Mode toggle */}
        <div className="flex items-center gap-2 mb-4">
          <button
            onClick={() => { stopAuto(); setMode("manual"); }}
            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all"
            style={mode === "manual" ? {
              background: "color-mix(in srgb, hsl(221 83% 53%) 12%, transparent)",
              border: "1px solid color-mix(in srgb, hsl(221 83% 53%) 25%, transparent)",
              color: "hsl(221 83% 53%)",
            } : { border: "1px solid hsl(var(--border))", color: "hsl(var(--muted-foreground))" }}
          >
            <Play className="h-3 w-3" /> Manual
          </button>
          <button
            onClick={() => { stopAuto(); setMode("auto"); }}
            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all"
            style={mode === "auto" ? {
              background: "color-mix(in srgb, hsl(38 92% 50%) 12%, transparent)",
              border: "1px solid color-mix(in srgb, hsl(38 92% 50%) 25%, transparent)",
              color: "hsl(38 92% 50%)",
            } : { border: "1px solid hsl(var(--border))", color: "hsl(var(--muted-foreground))" }}
          >
            <RefreshCw className="h-3 w-3" /> Auto
          </button>
        </div>

        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          {/* Agent steps */}
          <div className="flex items-center gap-2 flex-wrap">
            {AGENTS.map((a, i) => {
              const isDone   = doneAgents.includes(a.id);
              const isActive = currentAgent === a.id;
              return (
                <div key={a.id} className="flex items-center gap-2">
                  <div
                    className="flex items-center gap-2 rounded-lg px-3 py-2 transition-all"
                    style={{
                      background: isActive
                        ? `color-mix(in srgb, ${a.accent} 12%, transparent)`
                        : isDone
                        ? `color-mix(in srgb, ${a.accent} 6%, transparent)`
                        : "transparent",
                      border: `1px solid ${isActive || isDone ? `color-mix(in srgb, ${a.accent} 25%, transparent)` : "transparent"}`,
                      boxShadow: isActive ? `0 0 16px ${a.glow}` : undefined,
                    }}
                  >
                    {isDone ? (
                      <CheckCircle2 className="h-3.5 w-3.5" style={{ color: a.accent }} />
                    ) : isActive ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" style={{ color: a.accent }} />
                    ) : (
                      <Circle className="h-3.5 w-3.5 text-muted-foreground/40" />
                    )}
                    <div className="flex flex-col">
                      <span className="text-xs font-semibold leading-none" style={{ color: isActive || isDone ? a.accent : undefined }}>
                        {a.label}
                      </span>
                      <span className="text-[10px] text-muted-foreground">{a.role}</span>
                    </div>
                  </div>
                  {i < AGENTS.length - 1 && <div className="h-px w-4 bg-border hidden sm:block" />}
                </div>
              );
            })}
          </div>

          {/* Action area */}
          <div className="flex items-center gap-2 shrink-0">
            {mode === "auto" && (
              <div className="flex items-center gap-1.5">
                <Timer className="h-3.5 w-3.5 text-muted-foreground" />
                <div
                  className="flex items-center rounded-lg overflow-hidden"
                  style={{ border: "1px solid hsl(var(--border))", background: "hsl(222 47% 4%)" }}
                >
                  <button
                    onClick={() => !autoActive && setInterval_((v) => Math.max(10, v - 10))}
                    disabled={autoActive}
                    className="px-2 py-1 text-xs text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors disabled:opacity-40 disabled:cursor-not-allowed select-none"
                  >
                    −
                  </button>
                  <span className="w-10 text-center text-xs font-mono text-foreground select-none py-1">
                    {interval}
                  </span>
                  <button
                    onClick={() => !autoActive && setInterval_((v) => Math.min(3600, v + 10))}
                    disabled={autoActive}
                    className="px-2 py-1 text-xs text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors disabled:opacity-40 disabled:cursor-not-allowed select-none"
                  >
                    +
                  </button>
                </div>
                <span className="text-xs text-muted-foreground">sec</span>
              </div>
            )}

            {mode === "manual" ? (
              <Button
                onClick={runPipeline}
                disabled={running}
                className="rounded-full gap-2"
                style={!running ? {
                  background: "linear-gradient(135deg, hsl(221 83% 53%), hsl(188 94% 43%))",
                  boxShadow: "0 0 20px hsl(221 83% 53% / 0.3)",
                } : undefined}
              >
                {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                {running ? "Running…" : "Run Pipeline"}
              </Button>
            ) : autoActive ? (
              <Button
                onClick={stopAuto}
                className="rounded-full gap-2"
                style={{ background: "linear-gradient(135deg, hsl(0 84% 60%), hsl(38 92% 50%))", boxShadow: "0 0 20px hsl(0 84% 60% / 0.3)" }}
              >
                <Square className="h-3.5 w-3.5 fill-current" />
                Stop
                {countdown > 0 && !running && (
                  <span className="font-mono text-[10px] opacity-75">({countdown}s)</span>
                )}
              </Button>
            ) : (
              <Button
                onClick={startAuto}
                className="rounded-full gap-2"
                style={{
                  background: "linear-gradient(135deg, hsl(38 92% 50%), hsl(160 84% 39%))",
                  boxShadow: "0 0 20px hsl(38 92% 50% / 0.3)",
                }}
              >
                <RefreshCw className="h-4 w-4" />
                Start Auto
              </Button>
            )}
          </div>
        </div>

        {/* Guardian verify prompt — appears after remediation fires */}
        {remediatedService && !guardianRunning && !doneAgents.includes("guardian") && (
          <div className="mt-3 flex items-center gap-3 flex-wrap">
            <span className="flex items-center gap-1.5 text-[11px] font-mono" style={{ color: "hsl(280 84% 60%)" }}>
              <span className="h-1.5 w-1.5 rounded-full animate-pulse" style={{ background: "hsl(280 84% 60%)" }} />
              Remediation executed for <span className="font-bold">{remediatedService}</span> — Guardian ready to verify
            </span>
            <button
              onClick={() => runGuardian(remediatedService)}
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-semibold transition-all"
              style={{
                background: "color-mix(in srgb, hsl(280 84% 60%) 15%, transparent)",
                border: "1px solid color-mix(in srgb, hsl(280 84% 60%) 35%, transparent)",
                color: "hsl(280 84% 60%)",
                boxShadow: "0 0 12px hsl(280 84% 60% / 0.15)",
              }}
            >
              <ShieldCheck className="h-3 w-3" />
              Verify with Guardian
            </button>
          </div>
        )}
        {guardianRunning && (
          <div className="mt-3 flex items-center gap-2 text-[11px] font-mono" style={{ color: "hsl(280 84% 60%)" }}>
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Guardian verifying recovery…
          </div>
        )}

        {/* Status row */}
        {(done || autoActive) && (
          <div className="mt-3 flex items-center gap-3 text-xs font-medium flex-wrap">
            {done && (
              <span
                className="flex items-center gap-1.5"
                style={{ color: doneMsg.toLowerCase().includes("no anomaly") ? "hsl(188 94% 43%)" : "hsl(160 84% 39%)" }}
              >
                <CheckCircle2 className="h-3.5 w-3.5" />
                {doneMsg || "Pipeline complete"}
              </span>
            )}
            {autoActive && countdown > 0 && !running && (
              <span className="flex items-center gap-1.5 font-mono" style={{ color: "hsl(38 92% 50%)" }}>
                <Timer className="h-3.5 w-3.5" />
                Next run in {countdown}s
              </span>
            )}
            {autoActive && running && (
              <span className="flex items-center gap-1.5" style={{ color: "hsl(188 94% 43%)" }}>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Auto-running…
              </span>
            )}
          </div>
        )}
      </div>

      {error && (
        <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive shrink-0">
          {error}
        </div>
      )}

      {/* Terminal output */}
      <div
        ref={outputRef}
        className="relative flex flex-col flex-1 rounded-xl border border-border overflow-hidden"
        style={{ background: "hsl(222 47% 2%)" }}
      >
        {/* Terminal chrome bar */}
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border bg-card/50 shrink-0">
          <span className="h-2.5 w-2.5 rounded-full bg-destructive/60" />
          <span className="h-2.5 w-2.5 rounded-full bg-[hsl(var(--warning)/0.6)]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[hsl(var(--success)/0.6)]" />
          <span className="ml-3 font-mono text-[11px] text-muted-foreground">quantumstate — pipeline output</span>
          {cfg && (
            <span className="ml-auto flex items-center gap-1.5 font-mono text-[11px]" style={{ color: cfg.accent }}>
              <span className="h-1.5 w-1.5 rounded-full animate-pulse" style={{ background: cfg.accent }} />
              {cfg.label} active
            </span>
          )}
          {autoActive && !running && countdown > 0 && (
            <span className="ml-auto flex items-center gap-1.5 font-mono text-[11px]" style={{ color: "hsl(38 92% 50%)" }}>
              <Timer className="h-3 w-3" />
              next in {countdown}s
            </span>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-5 font-mono text-xs">
          {blocks.length === 0 && !running ? (
            <p className="py-16 text-center text-muted-foreground/50">
              $ awaiting pipeline execution…
            </p>
          ) : (
            <div className="flex flex-col gap-1.5">
              {blocks.map((b, i) => {
                const a = agentCfg(b.agent);
                if (b.event === "agent_start") {
                  return (
                    <div key={i} className={`${i > 0 ? "mt-4 pt-4 border-t border-border/50" : ""}`}>
                      <span className="text-sm font-bold" style={{ color: a.accent }}>▸ {b.text}</span>
                      <span className="text-muted-foreground/50 ml-2 text-[10px]">— {a.role}</span>
                    </div>
                  );
                }
                if (b.event === "reasoning") {
                  return (
                    <div key={i} className="pl-4 italic text-muted-foreground/60 text-[11px]">
                      ⟳ {b.text}
                    </div>
                  );
                }
                if (b.event === "remediation_triggered") {
                  const m = b.meta as Record<string, unknown> | undefined;
                  return (
                    <div
                      key={i}
                      className="my-2 rounded-lg p-3 border"
                      style={{
                        background: "color-mix(in srgb, hsl(160 84% 39%) 8%, transparent)",
                        borderColor: "color-mix(in srgb, hsl(160 84% 39%) 30%, transparent)",
                        boxShadow: "0 0 20px hsl(160 84% 39% / 0.1)",
                      }}
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <Zap className="h-3.5 w-3.5" style={{ color: "hsl(160 84% 39%)" }} />
                        <span className="text-[11px] font-bold uppercase tracking-wide" style={{ color: "hsl(160 84% 39%)" }}>
                          Autonomous Remediation Triggered
                        </span>
                      </div>
                      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] font-mono text-muted-foreground">
                        {m?.service  && <span>service  <span style={{ color: "hsl(160 84% 39%)" }}>{String(m.service)}</span></span>}
                        {m?.action   && <span>action   <span style={{ color: "hsl(160 84% 39%)" }}>{String(m.action)}</span></span>}
                        {m?.confidence !== undefined && <span>confidence <span style={{ color: "hsl(160 84% 39%)" }}>{(Number(m.confidence) * 100).toFixed(0)}%</span></span>}
                        {m?.risk_level && <span>risk <span style={{ color: m.risk_level === "high" ? "hsl(0 84% 60%)" : m.risk_level === "medium" ? "hsl(38 92% 50%)" : "hsl(160 84% 39%)" }}>{String(m.risk_level)}</span></span>}
                      </div>
                    </div>
                  );
                }
                if (b.event === "remediation_executing") {
                  const m = b.meta as Record<string, unknown> | undefined;
                  return (
                    <div
                      key={i}
                      className="my-1 rounded-lg px-3 py-2 border flex items-center gap-2"
                      style={{
                        background: "color-mix(in srgb, hsl(188 94% 43%) 6%, transparent)",
                        borderColor: "color-mix(in srgb, hsl(188 94% 43%) 20%, transparent)",
                      }}
                    >
                      <ShieldCheck className="h-3.5 w-3.5 shrink-0" style={{ color: "hsl(188 94% 43%)" }} />
                      <span className="text-[10px] font-mono" style={{ color: "hsl(188 94% 43%)" }}>
                        Recovery executing — exec_id: {String(m?.exec_id ?? "…")} · {String(m?.points ?? 0)} metric points written
                        {m?.wf_trigger ? " · workflow: triggered" : " · workflow: ES-direct"}
                      </span>
                    </div>
                  );
                }
                if (b.event === "guardian_verdict") {
                  const m = b.meta as Record<string, unknown> | undefined;
                  const isResolved = m?.verdict === "RESOLVED";
                  const accent = isResolved ? "hsl(280 84% 60%)" : "hsl(0 84% 60%)";
                  return (
                    <div
                      key={i}
                      className="my-2 rounded-lg p-3 border"
                      style={{
                        background: `color-mix(in srgb, ${accent} 8%, transparent)`,
                        borderColor: `color-mix(in srgb, ${accent} 30%, transparent)`,
                        boxShadow: `0 0 20px color-mix(in srgb, ${accent} 10%, transparent)`,
                      }}
                    >
                      <div className="flex items-center gap-2 mb-1.5">
                        <ShieldCheck className="h-3.5 w-3.5" style={{ color: accent }} />
                        <span className="text-[11px] font-bold uppercase tracking-wide" style={{ color: accent }}>
                          Guardian — {isResolved ? "RESOLVED" : "ESCALATE"}
                        </span>
                        {m?.mttr_fmt && (
                          <span className="ml-auto font-mono text-[10px]" style={{ color: accent }}>
                            MTTR {String(m.mttr_fmt)}
                          </span>
                        )}
                      </div>
                      {m?.summary && (
                        <p className="text-[10px] text-muted-foreground font-mono">{String(m.summary)}</p>
                      )}
                    </div>
                  );
                }
                if (b.event === "remediation_skipped") {
                  return (
                    <div key={i} className="pl-4 text-[11px] font-mono text-muted-foreground/50 italic">
                      ↷ {b.text}
                    </div>
                  );
                }
                if (b.event === "remediation_error") {
                  return (
                    <div
                      key={i}
                      className="my-1 rounded-lg px-3 py-2 border flex items-center gap-2"
                      style={{
                        background: "color-mix(in srgb, hsl(0 84% 60%) 8%, transparent)",
                        borderColor: "color-mix(in srgb, hsl(0 84% 60%) 25%, transparent)",
                      }}
                    >
                      <AlertTriangle className="h-3.5 w-3.5 shrink-0" style={{ color: "hsl(0 84% 60%)" }} />
                      <span className="text-[10px] font-mono" style={{ color: "hsl(0 84% 60%)" }}>{b.text}</span>
                    </div>
                  );
                }
                return (
                  <div key={i} className="pl-4 leading-relaxed text-foreground/80 whitespace-pre-wrap break-words">
                    {b.text}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
