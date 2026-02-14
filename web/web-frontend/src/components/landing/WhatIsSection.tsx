import { motion } from "framer-motion";
import AgentPipeline from "./AgentPipeline";

const pills = [
  "🔍 ES|QL anomaly detection",
  "🔗 Evidence chain correlation",
  "⚡ Sub-5-minute MTTR",
];

const WhatIsSection = () => {
  return (
    <section className="py-24 relative">
      <div className="container mx-auto px-4">
        <div className="grid lg:grid-cols-2 gap-16 items-center">
          {/* Text */}
          <motion.div
            initial={{ opacity: 0, x: -30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
          >
            <h2 className="text-3xl sm:text-4xl font-bold text-foreground mb-6">
              Autonomous SRE for modern infrastructure
            </h2>
            <div className="space-y-4 text-muted-foreground leading-relaxed">
              <p>
                Traditional incident response is reactive, manual, and slow. QuantumState flips the model:
                a pipeline of specialised agents continuously monitors your Elastic stack, correlates signals,
                and acts — with or without human approval.
              </p>
              <p>
                Built entirely on <span className="text-foreground font-semibold">Elastic Agent Builder</span>,
                every agent uses native ES|QL queries and tool-calling to investigate real data in your
                Elasticsearch cluster.
              </p>
            </div>

            <div className="flex flex-wrap gap-3 mt-8">
              {pills.map((pill) => (
                <span
                  key={pill}
                  className="px-4 py-2 rounded-full border border-border bg-muted/50 text-sm font-mono text-foreground"
                >
                  {pill}
                </span>
              ))}
            </div>
          </motion.div>

          {/* Pipeline */}
          <motion.div
            initial={{ opacity: 0, x: 30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6, delay: 0.2 }}
            className="flex justify-center"
          >
            <AgentPipeline />
          </motion.div>
        </div>
      </div>
    </section>
  );
};

export default WhatIsSection;
