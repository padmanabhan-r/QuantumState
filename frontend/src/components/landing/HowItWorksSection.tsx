import { motion } from "framer-motion";

const steps = [
  {
    step: "01",
    icon: "📡",
    label: "Detect",
    title: "Cassandra detects the anomaly",
    body: "Uses ES|QL window functions to compare current metrics against a 24-hour rolling baseline. Identifies memory leaks, error spikes, and latency degradation — with a confidence score and time-to-failure estimate.",
    accent: "hsl(221 83% 53%)",       // blue
    glow:   "hsl(221 83% 53% / 0.15)",
    tags:   ["Memory Leak Detection", "Error Spike Detection", "Time-to-Failure Forecast"],
  },
  {
    step: "02",
    icon: "🔬",
    label: "Investigate",
    title: "Archaeologist finds the root cause",
    body: "Searches error logs, correlates deployment events, and uses ELSER-powered hybrid search to surface semantically similar historical incidents — even when described in different language. Builds an evidence chain linking symptom to source.",
    accent: "hsl(188 94% 43%)",        // cyan
    glow:   "hsl(188 94% 43% / 0.15)",
    tags:   ["Error Log Search", "Deployment Correlation", "ELSER Semantic Incident Match"],
  },
  {
    step: "03",
    icon: "🩺",
    label: "Resolve",
    title: "Surgeon triggers the fix",
    body: "Retrieves the most relevant runbook via ELSER semantic search, samples current metrics, then — at confidence ≥ 0.8 — triggers the Elastic Workflow directly. The Workflow creates a Kibana Case and hands off to the MCP Runner for actual container restart.",
    accent: "hsl(160 84% 39%)",        // green
    glow:   "hsl(160 84% 39% / 0.15)",
    tags:   ["ELSER Runbook Retrieval", "Workflow Trigger (conf ≥ 0.8)", "Remediation Audit Log"],
  },
  {
    step: "04",
    icon: "🛡️",
    label: "Verify",
    title: "Guardian closes the loop",
    body: "60 seconds after remediation fires, Guardian runs structured post-fix verification. Checks memory, error rate, and latency against recovery thresholds, calculates MTTR, and returns a RESOLVED or ESCALATE verdict to the incident record.",
    accent: "hsl(280 84% 60%)",        // purple
    glow:   "hsl(280 84% 60% / 0.15)",
    tags:   ["Post-Fix Metric Verification", "MTTR Calculation", "Incident Closure"],
  },
];

const HowItWorksSection = () => {
  return (
    <section className="py-24 relative">
      <div className="container mx-auto px-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center mb-16"
        >
          <h2 className="text-3xl sm:text-4xl font-bold text-foreground mb-4">How It Works</h2>
          <p className="text-muted-foreground max-w-xl mx-auto">
            Four stages. Four live agents. Fully closed loop.
          </p>
        </motion.div>

        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 relative">
          {/* Connector line between cards on desktop */}
          <div className="hidden lg:block absolute top-10 left-[calc(25%+12px)] right-[calc(25%+12px)] h-px"
            style={{ background: "linear-gradient(90deg, hsl(221 83% 53% / 0.4), hsl(188 94% 43% / 0.4), hsl(160 84% 39% / 0.4), hsl(280 84% 60% / 0.4))" }}
          />

          {steps.map((step, i) => (
            <motion.div
              key={step.title}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: i * 0.15 }}
              whileHover={{ y: -8, transition: { duration: 0.2 } }}
              className="relative flex flex-col gap-5 rounded-xl p-6 overflow-hidden cursor-default"
              style={{
                background: `linear-gradient(135deg, hsl(222 47% 5%), hsl(222 47% 7%))`,
                border: `1px solid ${step.accent}33`,
                boxShadow: `0 0 0 1px ${step.accent}11, 0 8px 32px ${step.glow}`,
              }}
            >
              {/* Top accent bar */}
              <div
                className="absolute top-0 left-0 right-0 h-[2px]"
                style={{ background: `linear-gradient(90deg, transparent, ${step.accent}, transparent)` }}
              />

              {/* Step number + icon row */}
              <div className="flex items-start justify-between">
                {/* Large icon in a glowing circle */}
                <div
                  className="flex h-14 w-14 items-center justify-center rounded-xl text-2xl"
                  style={{
                    background: `${step.accent}18`,
                    border: `1px solid ${step.accent}30`,
                    boxShadow: `0 0 20px ${step.glow}`,
                  }}
                >
                  {step.icon}
                </div>

                {/* Step counter */}
                <span
                  className="font-mono text-4xl font-bold leading-none select-none"
                  style={{ color: `${step.accent}25` }}
                >
                  {step.step}
                </span>
              </div>

              {/* Label pill */}
              <div>
                <span
                  className="inline-block rounded-full px-3 py-0.5 text-[10px] font-semibold uppercase tracking-widest"
                  style={{
                    background: `${step.accent}18`,
                    color: step.accent,
                    border: `1px solid ${step.accent}30`,
                  }}
                >
                  {step.label}
                </span>
              </div>

              {/* Title */}
              <h3 className="text-base font-semibold text-foreground leading-snug">{step.title}</h3>

              {/* Body */}
              <p className="text-sm text-muted-foreground leading-relaxed flex-1">{step.body}</p>

              {/* Bottom tags */}
              <div
                className="mt-auto pt-4 border-t flex flex-col gap-1"
                style={{ borderColor: `${step.accent}20` }}
              >
                {step.tags.map((t) => (
                  <span
                    key={t}
                    className="font-mono text-[10px] tracking-wide flex items-center gap-1.5"
                    style={{ color: `${step.accent}90` }}
                  >
                    <span style={{ color: step.accent }}>›</span>
                    {t}
                  </span>
                ))}
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default HowItWorksSection;
