import { Link } from "react-router-dom";
import { ArrowLeft, Zap, Play, MessageSquare, Activity } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import ElasticIcon from "@/components/ElasticIcon";
import MttrStats from "@/components/console/MttrStats";
import IncidentFeed from "@/components/console/IncidentFeed";
import PipelinePanel from "@/components/console/PipelinePanel";
import ChatPanel from "@/components/console/ChatPanel";

const AGENTS = [
  { name: "Cassandra",     role: "Detection",    color: "hsl(221 83% 53%)" },
  { name: "Archaeologist", role: "Investigation", color: "hsl(188 94% 43%)" },
  { name: "Surgeon",       role: "Remediation",  color: "hsl(160 84% 39%)" },
];

const Console = () => {
  return (
    <div className="min-h-screen flex flex-col">

      {/* ── Sticky header ── */}
      <header className="sticky top-0 z-50 flex h-14 items-center gap-4 border-b border-border bg-background/80 px-6 backdrop-blur-xl">
        <Link
          to="/"
          className="flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Home
        </Link>

        <div className="mx-2 h-4 w-px bg-border" />

        <div className="flex items-center gap-1.5">
          <Zap className="h-4 w-4 text-secondary fill-secondary" />
          <span className="text-gradient-blue font-bold">QuantumState</span>
          <span className="rounded border border-primary/20 bg-primary/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-primary">
            SRE Console
          </span>
        </div>

        <div className="ml-auto flex items-center gap-3">
          <span className="hidden sm:flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground">
            <ElasticIcon size={13} /> Elastic Agent Builder
          </span>
          <div className="h-3 w-px bg-border hidden sm:block" />
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span className="h-2 w-2 rounded-full bg-[hsl(var(--success))] shadow-[0_0_8px_hsl(var(--success))] animate-pulse" />
            Live
          </span>
        </div>
      </header>

      {/* ── Hero banner ── */}
      <div className="hero-grid-bg border-b border-border px-6 py-8">
        <div className="mx-auto max-w-5xl">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-6">
            {/* Left — title + agent pills */}
            <div className="flex flex-col gap-3">
              <div className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-primary animate-pulse" />
                <span className="text-xs font-mono text-muted-foreground uppercase tracking-widest">
                  Autonomous SRE · Active
                </span>
              </div>
              <h1 className="text-2xl font-bold text-foreground">
                Incident Command Centre
              </h1>
              <div className="flex flex-wrap gap-2 mt-1">
                {AGENTS.map((a) => (
                  <span
                    key={a.name}
                    className="flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium"
                    style={{
                      background: `color-mix(in srgb, ${a.color} 12%, transparent)`,
                      border: `1px solid color-mix(in srgb, ${a.color} 30%, transparent)`,
                      color: a.color,
                    }}
                  >
                    <span className="h-1.5 w-1.5 rounded-full animate-pulse" style={{ background: a.color }} />
                    {a.name}
                    <span className="opacity-50">· {a.role}</span>
                  </span>
                ))}
              </div>
            </div>

            {/* Right — MTTR stats */}
            <MttrStats />
          </div>
        </div>
      </div>

      {/* ── Main content ── */}
      <main className="flex-1 px-6 py-8 mx-auto w-full max-w-5xl">
        <Tabs defaultValue="incidents">
          <TabsList className="mb-8 h-11 bg-card border border-border p-1 gap-1">
            <TabsTrigger
              value="incidents"
              className="gap-2 rounded-md px-4 data-[state=active]:bg-primary/15 data-[state=active]:text-primary data-[state=active]:border data-[state=active]:border-primary/30"
            >
              <Zap className="h-3.5 w-3.5" />
              Incident Feed
            </TabsTrigger>
            <TabsTrigger
              value="pipeline"
              className="gap-2 rounded-md px-4 data-[state=active]:bg-secondary/15 data-[state=active]:text-secondary data-[state=active]:border data-[state=active]:border-secondary/30"
            >
              <Play className="h-3.5 w-3.5" />
              Run Pipeline
            </TabsTrigger>
            <TabsTrigger
              value="chat"
              className="gap-2 rounded-md px-4 data-[state=active]:bg-[hsl(var(--success)/0.15)] data-[state=active]:text-[hsl(var(--success))] data-[state=active]:border data-[state=active]:border-[hsl(var(--success)/0.3)]"
            >
              <MessageSquare className="h-3.5 w-3.5" />
              Chat with Agents
            </TabsTrigger>
          </TabsList>

          <TabsContent value="incidents">
            <IncidentFeed />
          </TabsContent>
          <TabsContent value="pipeline">
            <PipelinePanel />
          </TabsContent>
          <TabsContent value="chat">
            <ChatPanel />
          </TabsContent>
        </Tabs>
      </main>

      {/* ── Footer ── */}
      <footer className="border-t border-border px-6 py-3 flex justify-between items-center">
        <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <Zap className="h-3 w-3 text-secondary fill-secondary" />
          QuantumState SRE Console
        </span>
        <span className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground">
          <ElasticIcon size={12} /> Powered by Elastic Agent Builder
        </span>
      </footer>
    </div>
  );
};

export default Console;
