import { Link } from "react-router-dom";
import { useState, useEffect } from "react";
import { ArrowLeft, Zap, Play, Activity, Shield, KeyRound } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import ElasticIcon from "@/components/ElasticIcon";
import { Button } from "@/components/ui/button";
import CredentialsModal from "@/components/CredentialsModal";
import { useCredentials } from "@/contexts/CredentialsContext";
import IncidentFeed from "@/components/console/IncidentFeed";
import PipelinePanel from "@/components/console/PipelinePanel";
import ActionsPanel from "@/components/console/ActionsPanel";
import MttrStats from "@/components/console/MttrStats";

const AGENTS = [
  { name: "Cassandra",     role: "Detection",    color: "hsl(221 83% 53%)" },
  { name: "Archaeologist", role: "Investigation", color: "hsl(188 94% 43%)" },
  { name: "Surgeon",       role: "Remediation",  color: "hsl(160 84% 39%)" },
  { name: "Guardian",      role: "Verification", color: "hsl(280 84% 60%)" },
];

const Console = () => {
  const [now, setNow] = useState(new Date());
  const [credsOpen, setCredsOpen] = useState(false);
  const { isCustom } = useCredentials();

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="h-screen overflow-hidden flex flex-col">

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
          <Button
            variant="outline"
            size="sm"
            className={`h-7 gap-1.5 text-xs ${isCustom ? "border-primary/40 text-primary" : "text-muted-foreground"}`}
            onClick={() => setCredsOpen(true)}
          >
            <KeyRound className="h-3 w-3" />
            {isCustom ? "Custom cluster" : "Connect"}
          </Button>
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span className="h-2 w-2 rounded-full bg-[hsl(var(--success))] shadow-[0_0_8px_hsl(var(--success))] animate-pulse" />
            Live
          </span>
        </div>
      </header>

      <CredentialsModal open={credsOpen} onClose={() => setCredsOpen(false)} />

      {/* ── Hero banner ── */}
      <div className="hero-grid-bg border-b border-border px-4 sm:px-6 py-2 sm:py-4 shrink-0">
        <div className="flex items-center gap-4">
          {/* Left — title + agent pills */}
          <div className="flex flex-col gap-1.5 sm:gap-2 min-w-0">
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-primary animate-pulse shrink-0" />
              <h1 className="text-sm sm:text-xl font-bold text-foreground truncate">
                Incident Command Centre
              </h1>
              <span className="hidden md:block text-xs font-mono text-muted-foreground uppercase tracking-widest whitespace-nowrap">
                · Autonomous SRE · Active
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {AGENTS.map((a) => (
                <span
                  key={a.name}
                  className="flex items-center gap-1.5 rounded-full px-2 sm:px-3 py-0.5 sm:py-1 text-xs font-medium whitespace-nowrap"
                  style={{
                    background: `color-mix(in srgb, ${a.color} 12%, transparent)`,
                    border: `1px solid color-mix(in srgb, ${a.color} 30%, transparent)`,
                    color: a.color,
                  }}
                >
                  <span className="h-1.5 w-1.5 rounded-full animate-pulse shrink-0" style={{ background: a.color }} />
                  {a.name}
                  <span className="hidden sm:inline opacity-50">· {a.role}</span>
                </span>
              ))}
            </div>
          </div>

          {/* Right — live clock */}
          <div className="ml-auto shrink-0 hidden sm:flex flex-col items-end">
            <span className="font-mono text-lg sm:text-2xl font-bold text-foreground tabular-nums leading-none">
              {now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
            </span>
            <span className="font-mono text-[10px] text-muted-foreground tracking-wider">
              {now.toLocaleDateString([], { weekday: "short", year: "numeric", month: "short", day: "numeric" })}
            </span>
          </div>
        </div>
      </div>

      {/* ── MTTR stats strip ── */}
      <div className="border-b border-border bg-card/20 px-6 py-3 shrink-0">
        <MttrStats />
      </div>

      {/* ── Main two-panel layout ── */}
      <main className="flex flex-1 overflow-hidden">

        {/* Left panel — Pipeline */}
        <div className="flex-1 min-w-0 flex flex-col overflow-hidden border-r border-border">
          <div className="border-b border-border bg-card/40 px-4 py-2 shrink-0 flex items-center gap-2">
            <Play className="h-3 w-3 text-secondary" />
            <span className="text-xs font-medium text-secondary">Run Pipeline</span>
          </div>
          <div className="flex flex-col flex-1 overflow-hidden p-6">
            <PipelinePanel />
          </div>
        </div>

        {/* Right panel — Incidents + Actions tabs */}
        <div className="w-[240px] md:w-[320px] lg:w-[400px] xl:w-[460px] shrink-0 flex flex-col overflow-hidden">
          <Tabs defaultValue="incidents" className="flex flex-col h-full overflow-hidden">
            <div className="border-b border-border bg-card/40 px-4 py-2 shrink-0">
              <TabsList className="h-9 bg-background/60 border border-border p-1 gap-1">
                <TabsTrigger
                  value="incidents"
                  className="gap-1.5 rounded-md px-3 text-xs data-[state=active]:bg-primary/15 data-[state=active]:text-primary data-[state=active]:border data-[state=active]:border-primary/30"
                >
                  <Zap className="h-3 w-3" />
                  Incidents
                </TabsTrigger>
                <TabsTrigger
                  value="actions"
                  className="gap-1.5 rounded-md px-3 text-xs data-[state=active]:bg-emerald-500/15 data-[state=active]:text-emerald-400 data-[state=active]:border data-[state=active]:border-emerald-500/30"
                >
                  <Shield className="h-3 w-3" />
                  Actions
                </TabsTrigger>
              </TabsList>
            </div>
            <TabsContent value="incidents" className="flex-1 overflow-y-auto p-4 mt-0 data-[state=inactive]:hidden">
              <IncidentFeed />
            </TabsContent>
            <TabsContent value="actions" className="flex-1 overflow-y-auto p-4 mt-0 data-[state=inactive]:hidden">
              <ActionsPanel />
            </TabsContent>
          </Tabs>
        </div>
      </main>

      {/* ── Footer ── */}
      <footer className="hidden sm:flex border-t border-border px-4 sm:px-6 py-2 sm:py-3 justify-between items-center shrink-0">
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
