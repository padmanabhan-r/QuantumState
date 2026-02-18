import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Send, Loader2, MessageSquare, User } from "lucide-react";
import { sendChat } from "@/lib/api";

interface Message {
  role: "user" | "agent";
  content: string;
  agent?: string;
  error?: boolean;
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

export default function ChatPanel() {
  const [agentId, setAgentId]   = useState("cassandra");
  const [input, setInput]       = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading]   = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: text }]);
    setLoading(true);

    try {
      const res = await sendChat(agentId, text);
      if (res.error) {
        const errText = typeof res.error === "string" ? res.error : (res.error as { message?: string })?.message ?? JSON.stringify(res.error);
        setMessages((m) => [...m, { role: "agent", content: errText, agent: agentId, error: true }]);
      } else {
        setMessages((m) => [...m, { role: "agent", content: res.response ?? "(no response)", agent: agentId }]);
      }
    } catch (err) {
      setMessages((m) => [
        ...m,
        { role: "agent", content: err instanceof Error ? err.message : "Unknown error", agent: agentId, error: true },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  }

  const active = agentCfg(agentId);

  return (
    <div className="flex flex-col gap-4 h-full">

      {/* Agent selector */}
      <div
        className="rounded-xl p-4 border border-border shrink-0"
        style={{ background: "linear-gradient(135deg, hsl(222 47% 4%), hsl(222 47% 6%))" }}
      >
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div className="flex flex-col gap-1">
            <span className="text-xs font-mono uppercase tracking-widest text-muted-foreground">Talk to agent</span>
            <span className="text-sm font-semibold text-foreground">Select an agent to query</span>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {AGENTS.map((a) => {
              const isSelected = agentId === a.id;
              return (
                <button
                  key={a.id}
                  onClick={() => setAgentId(a.id)}
                  className="flex items-center gap-2 rounded-lg px-3 py-2 transition-all"
                  style={{
                    background: isSelected
                      ? `color-mix(in srgb, ${a.accent} 12%, transparent)`
                      : "transparent",
                    border: `1px solid ${isSelected ? `color-mix(in srgb, ${a.accent} 25%, transparent)` : "hsl(var(--border))"}`,
                    boxShadow: isSelected ? `0 0 16px ${a.glow}` : undefined,
                  }}
                >
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{
                      background: a.accent,
                      boxShadow: isSelected ? `0 0 6px ${a.accent}` : undefined,
                      opacity: isSelected ? 1 : 0.4,
                    }}
                  />
                  <div className="flex flex-col text-left">
                    <span
                      className="text-xs font-semibold leading-none"
                      style={{ color: isSelected ? a.accent : undefined }}
                    >
                      {a.label}
                    </span>
                    <span className="text-[10px] text-muted-foreground">{a.role}</span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Chat window */}
      <div
        className="relative flex flex-col flex-1 rounded-xl border border-border overflow-hidden"
        style={{ background: "hsl(222 47% 2%)" }}
      >
        {/* Chrome bar */}
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border bg-card/50">
          <span className="h-2.5 w-2.5 rounded-full bg-destructive/60" />
          <span className="h-2.5 w-2.5 rounded-full bg-[hsl(var(--warning)/0.6)]" />
          <span className="h-2.5 w-2.5 rounded-full bg-[hsl(var(--success)/0.6)]" />
          <span className="ml-3 font-mono text-[11px] text-muted-foreground">
            quantumstate — agent chat
          </span>
          <span
            className="ml-auto flex items-center gap-1.5 font-mono text-[11px]"
            style={{ color: active.accent }}
          >
            <span className="h-1.5 w-1.5 rounded-full animate-pulse" style={{ background: active.accent }} />
            {active.label} · {active.role}
          </span>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-4 font-mono text-xs">
          {messages.length === 0 && !loading ? (
            <div className="flex flex-col items-center justify-center h-full py-16 gap-3">
              <div
                className="h-10 w-10 rounded-full flex items-center justify-center"
                style={{
                  background: `color-mix(in srgb, ${active.accent} 12%, transparent)`,
                  border: `1px solid color-mix(in srgb, ${active.accent} 25%, transparent)`,
                  boxShadow: `0 0 20px ${active.glow}`,
                }}
              >
                <MessageSquare className="h-4 w-4" style={{ color: active.accent }} />
              </div>
              <p className="text-muted-foreground/50 text-center">
                Ask {active.label} about the current incident
              </p>
            </div>
          ) : (
            <>
              {messages.map((msg, i) => {
                if (msg.role === "user") {
                  return (
                    <div key={i} className="flex flex-col items-end gap-1">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[10px] uppercase tracking-wider text-primary/60">You</span>
                        <User className="h-3 w-3 text-primary/60" />
                      </div>
                      <div
                        className="max-w-[82%] rounded-xl px-4 py-2.5 text-xs leading-relaxed whitespace-pre-wrap break-words"
                        style={{
                          background: "color-mix(in srgb, hsl(221 83% 53%) 12%, transparent)",
                          border: "1px solid color-mix(in srgb, hsl(221 83% 53%) 25%, transparent)",
                          color: "hsl(var(--foreground))",
                        }}
                      >
                        {msg.content}
                      </div>
                    </div>
                  );
                }

                const a = agentCfg(msg.agent ?? "cassandra");
                return (
                  <div key={i} className="flex flex-col items-start gap-1">
                    <div className="flex items-center gap-1.5">
                      <span
                        className="h-3.5 w-3.5 rounded-full flex items-center justify-center text-[8px] font-bold"
                        style={{
                          background: `color-mix(in srgb, ${a.accent} 20%, transparent)`,
                          color: a.accent,
                          border: `1px solid color-mix(in srgb, ${a.accent} 40%, transparent)`,
                        }}
                      >
                        ▸
                      </span>
                      <span className="text-[10px] uppercase tracking-wider" style={{ color: a.accent }}>
                        {a.label}
                      </span>
                    </div>
                    <div
                      className="max-w-[82%] rounded-xl px-4 py-2.5 text-xs leading-relaxed whitespace-pre-wrap break-words"
                      style={msg.error ? {
                        background: "hsl(var(--destructive) / 0.1)",
                        border: "1px solid hsl(var(--destructive) / 0.3)",
                        color: "hsl(var(--destructive))",
                      } : {
                        background: `color-mix(in srgb, ${a.accent} 6%, transparent)`,
                        border: `1px solid color-mix(in srgb, ${a.accent} 15%, transparent)`,
                        color: "hsl(var(--foreground) / 0.85)",
                      }}
                    >
                      {msg.content}
                    </div>
                  </div>
                );
              })}

              {loading && (
                <div className="flex flex-col items-start gap-1">
                  <div className="flex items-center gap-1.5">
                    <span
                      className="h-3.5 w-3.5 rounded-full flex items-center justify-center text-[8px] font-bold"
                      style={{
                        background: `color-mix(in srgb, ${active.accent} 20%, transparent)`,
                        color: active.accent,
                        border: `1px solid color-mix(in srgb, ${active.accent} 40%, transparent)`,
                      }}
                    >
                      ▸
                    </span>
                    <span className="text-[10px] uppercase tracking-wider" style={{ color: active.accent }}>
                      {active.label}
                    </span>
                  </div>
                  <div
                    className="flex items-center gap-2 rounded-xl px-4 py-2.5"
                    style={{
                      background: `color-mix(in srgb, ${active.accent} 6%, transparent)`,
                      border: `1px solid color-mix(in srgb, ${active.accent} 15%, transparent)`,
                    }}
                  >
                    <Loader2 className="h-3 w-3 animate-spin" style={{ color: active.accent }} />
                    <span className="text-muted-foreground/60">Processing query…</span>
                  </div>
                </div>
              )}
            </>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input area */}
        <div className="border-t border-border p-4 bg-card/30">
          <div className="flex gap-3 items-end">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKey}
              placeholder={`Ask ${active.label} about the current incident…`}
              rows={2}
              className="resize-none text-sm bg-transparent border-border/60 focus:border-[color:var(--active-accent)] font-mono"
              style={{ "--active-accent": active.accent } as React.CSSProperties}
            />
            <Button
              onClick={handleSend}
              disabled={loading || !input.trim()}
              size="icon"
              className="h-10 w-10 shrink-0 rounded-lg"
              style={!loading && input.trim() ? {
                background: `linear-gradient(135deg, ${active.accent}, color-mix(in srgb, ${active.accent} 70%, hsl(221 83% 53%)))`,
                boxShadow: `0 0 16px ${active.glow}`,
              } : undefined}
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          </div>
          <p className="mt-2 text-[10px] text-muted-foreground/40 font-mono">
            ↵ Enter to send · Shift+Enter for newline
          </p>
        </div>
      </div>
    </div>
  );
}
