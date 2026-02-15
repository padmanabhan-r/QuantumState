import { motion } from "framer-motion";
import { Badge } from "@/components/ui/badge";

const agents = [
  { name: "Cassandra",     role: "Detection",    icon: "📡", delay: 0,   status: "live"    as const },
  { name: "Archaeologist", role: "Investigation", icon: "🔬", delay: 0.1, status: "live"    as const },
  { name: "Surgeon",       role: "Remediation",  icon: "🩺", delay: 0.2, status: "live"    as const },
  { name: "Guardian",      role: "Verification", icon: "🛡️", delay: 0.3, status: "live"    as const },
  { name: "Tactician",     role: "Decision",     icon: "🧠", delay: 0.4, status: "roadmap" as const },
  { name: "Diplomat",      role: "Approval Gate",icon: "🤝", delay: 0.5, status: "roadmap" as const },
];

// Animated arrow: three chevrons fade in sequentially top→bottom
function FlowArrow() {
  return (
    <div className="relative h-8 flex flex-col items-center justify-center gap-0.5">
      {[0, 1, 2].map((n) => (
        <motion.svg
          key={n}
          width="12"
          height="7"
          viewBox="0 0 12 7"
          fill="none"
          animate={{ opacity: [0.15, 1, 0.15] }}
          transition={{
            duration: 1.2,
            repeat: Infinity,
            delay: n * 0.3,
            ease: "easeInOut",
          }}
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
  );
}

// Dashed separator + "Roadmap" label between live and future agents
function RoadmapDivider() {
  return (
    <div className="flex flex-col items-center gap-1 py-1">
      {/* Dashed line segment */}
      <div className="h-3 w-px border-l border-dashed border-warning/40" />

      {/* Label */}
      <div className="flex items-center gap-2">
        <div className="h-px w-8 bg-warning/30" />
        <span className="text-[10px] font-semibold uppercase tracking-widest text-warning/60">
          Roadmap
        </span>
        <div className="h-px w-8 bg-warning/30" />
      </div>

      {/* Dashed line segment */}
      <div className="h-3 w-px border-l border-dashed border-warning/40" />
    </div>
  );
}

const AgentPipeline = () => {
  return (
    <div className="flex flex-col items-center gap-0">
      {agents.map((agent, i) => (
        <div key={agent.name} className="flex flex-col items-center">
          <motion.div
            initial={{ opacity: 0, x: 30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5, delay: agent.delay }}
            whileHover={{
              y: -4,
              boxShadow:
                agent.status === "live"
                  ? "0 0 30px hsl(221 83% 53% / 0.3)"
                  : "0 0 20px hsl(38 92% 50% / 0.15)",
            }}
            className={`px-6 py-4 flex items-center gap-4 min-w-[220px] cursor-default transition-all rounded-lg ${
              agent.status === "live"
                ? "card-surface"
                : "bg-card border border-dashed border-warning/40 opacity-50"
            }`}
          >
            <span className="text-2xl">{agent.icon}</span>
            <div className="flex-1">
              <p className="font-semibold text-foreground font-mono text-sm">{agent.name}</p>
              <p className="text-xs text-muted-foreground">{agent.role}</p>
            </div>
            <Badge
              className={
                agent.status === "live"
                  ? "bg-success/20 text-success border-success/30 text-[10px]"
                  : "bg-warning/20 text-warning border-warning/30 text-[10px]"
              }
            >
              {agent.status === "live" ? "Live" : "Roadmap"}
            </Badge>
          </motion.div>

          {/* Connector below each card except the last */}
          {i < agents.length - 1 && (
            i === 3
              ? <RoadmapDivider />   // Between Guardian (live) and Tactician (roadmap)
              : <FlowArrow />        // Between all other agents
          )}
        </div>
      ))}
    </div>
  );
};

export default AgentPipeline;
