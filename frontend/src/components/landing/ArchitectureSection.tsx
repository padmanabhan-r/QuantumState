import { motion } from "framer-motion";
import ElasticIcon from "@/components/ElasticIcon";

const liveAgents    = ["Cassandra", "Archaeologist", "Surgeon", "Guardian"];
const roadmapAgents = ["Tactician", "Diplomat"];
const indices = [
  { label: "Service Metrics",      desc: "CPU, memory, error rate, latency — time-series per service" },
  { label: "Application Logs",     desc: "Structured logs with severity, trace IDs and stack traces" },
  { label: "Incident Reports",     desc: "Resolved incidents with MTTR, root cause and audit trail" },
  { label: "Agent Decisions",      desc: "Every agent action logged for compliance and post-mortem" },
  { label: "Remediation Actions",  desc: "Executed fixes with exec_id, risk level, and workflow status" },
  { label: "Remediation Results",  desc: "Guardian verdicts — RESOLVED / ESCALATE with MTTR evidence" },
];

const ArchitectureSection = () => {
  return (
    <section className="py-24 relative">
      <div className="container mx-auto px-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center mb-16"
        >
          <h2 className="text-3xl sm:text-4xl font-bold text-foreground mb-4 flex items-center justify-center gap-3">
            <ElasticIcon size={36} /> Built on Elastic Agent Builder
          </h2>
          <p className="text-muted-foreground max-w-2xl mx-auto">
            Every agent is a native Elastic Agent Builder agent — no external LLM orchestration.
            All intelligence runs inside your Elastic cluster.
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
          className="max-w-3xl mx-auto"
        >
          {/* Top layer — Agent Builder box */}
          <div className="card-surface border-glow-top p-6 rounded-t-lg">
            <p className="text-xs text-muted-foreground font-mono mb-4 flex items-center justify-center gap-1.5">
              <ElasticIcon size={14} /> Elastic Agent Builder
            </p>

            {/* Live agents */}
            <div className="flex flex-wrap justify-center gap-2 mb-3">
              {liveAgents.map((a) => (
                <span
                  key={a}
                  className="px-3 py-1.5 rounded-md bg-muted text-xs font-mono text-foreground border border-border flex items-center gap-1.5"
                >
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-[hsl(var(--success))]" />
                  {a}
                </span>
              ))}
            </div>

            {/* Divider */}
            <div className="flex items-center gap-2 my-2 px-4">
              <div className="h-px flex-1 border-t border-dashed border-warning/30" />
              <span className="text-[10px] font-semibold uppercase tracking-widest text-warning/50">
                Roadmap
              </span>
              <div className="h-px flex-1 border-t border-dashed border-warning/30" />
            </div>

            {/* Roadmap agents */}
            <div className="flex flex-wrap justify-center gap-2 mt-3">
              {roadmapAgents.map((a) => (
                <span
                  key={a}
                  className="px-3 py-1.5 rounded-md bg-muted/50 text-xs font-mono text-muted-foreground border border-dashed border-warning/30 opacity-60 flex items-center gap-1.5"
                >
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-[hsl(var(--warning)/0.5)]" />
                  {a}
                </span>
              ))}
            </div>
          </div>

          {/* Connector with downward chevron animation */}
          <div className="flex flex-col items-center">
            <div className="h-3 w-px bg-border" />
            <p className="text-[10px] font-mono text-muted-foreground px-2">ES|QL + Tool Calls</p>
            <div className="flex flex-col items-center gap-0.5 py-1">
              {[0, 1, 2].map((n) => (
                <motion.svg
                  key={n}
                  width="12"
                  height="7"
                  viewBox="0 0 12 7"
                  fill="none"
                  animate={{ opacity: [0.15, 1, 0.15] }}
                  transition={{ duration: 1.2, repeat: Infinity, delay: n * 0.3, ease: "easeInOut" }}
                >
                  <path
                    d="M1 1L6 6L11 1"
                    stroke="hsl(var(--primary))"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </motion.svg>
              ))}
            </div>
            <div className="h-3 w-px bg-border" />
          </div>

          {/* Bottom layer — Elasticsearch */}
          <div className="card-surface border-glow-top p-6 rounded-b-lg">
            <p className="text-xs text-muted-foreground font-mono mb-3 text-center">
              Elasticsearch 9.x
            </p>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {indices.map((idx) => (
                <div
                  key={idx.label}
                  className="rounded-lg bg-muted border border-border px-4 py-3 flex flex-col gap-1"
                >
                  <span className="text-xs font-semibold text-foreground">{idx.label}</span>
                  <span className="text-[11px] text-muted-foreground leading-snug">{idx.desc}</span>
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
};

export default ArchitectureSection;
