import { useState, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Play, Loader2, CheckCircle2, Circle } from "lucide-react";

interface Block { agent: string; event: string; text: string; }

const AGENTS = [
  { id: "cassandra",     label: "Cassandra",     role: "Detection",    accent: "hsl(221 83% 53%)", glow: "hsl(221 83% 53% / 0.15)" },
  { id: "archaeologist", label: "Archaeologist", role: "Investigation", accent: "hsl(188 94% 43%)", glow: "hsl(188 94% 43% / 0.15)" },
  { id: "surgeon",       label: "Surgeon",       role: "Remediation",  accent: "hsl(160 84% 39%)", glow: "hsl(160 84% 39% / 0.15)" },
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
  const [error, setError]               = useState<string | null>(null);
  const outputRef = useRef<HTMLDivElement>(null);

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
    setRunning(true); setDone(false); setError(null);
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
                setDone(true); setCurrentAgent(null);
              } else if (evtName === "error") {
                setError(text);
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

  const cfg = currentAgent ? agentCfg(currentAgent) : null;

  return (
    <div className="flex flex-col gap-6">
      {/* Agent progress tracker */}
      <div
        className="rounded-xl p-5 border border-border"
        style={{ background: "linear-gradient(135deg, hsl(222 47% 4%), hsl(222 47% 6%))" }}
      >
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          {/* Agent steps */}
          <div className="flex items-center gap-2 flex-wrap">
            {AGENTS.map((a, i) => {
              const isDone    = doneAgents.includes(a.id);
              const isActive  = currentAgent === a.id;
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
                  {i < AGENTS.length - 1 && (
                    <div className="h-px w-4 bg-border hidden sm:block" />
                  )}
                </div>
              );
            })}
          </div>

          {/* Run button */}
          <Button
            onClick={runPipeline}
            disabled={running}
            className="rounded-full gap-2 shrink-0"
            style={!running ? {
              background: "linear-gradient(135deg, hsl(221 83% 53%), hsl(188 94% 43%))",
              boxShadow: "0 0 20px hsl(221 83% 53% / 0.3)",
            } : undefined}
          >
            {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {running ? "Running…" : "Run Pipeline"}
          </Button>
        </div>

        {done && (
          <div className="mt-3 flex items-center gap-2 text-xs font-medium"
            style={{ color: "hsl(160 84% 39%)" }}>
            <CheckCircle2 className="h-4 w-4" />
            Pipeline complete — incident report written to Elasticsearch
          </div>
        )}
      </div>

      {error && (
        <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Terminal output */}
      <div
        ref={outputRef}
        className="relative rounded-xl border border-border overflow-hidden"
        style={{ background: "hsl(222 47% 2%)" }}
      >
        {/* Terminal chrome bar */}
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border bg-card/50">
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
        </div>

        <div className="min-h-[360px] max-h-[480px] overflow-y-auto p-5 font-mono text-xs">
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
                      <span className="text-sm font-bold" style={{ color: a.accent }}>
                        ▸ {b.text}
                      </span>
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
