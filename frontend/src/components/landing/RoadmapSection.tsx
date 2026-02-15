import { motion } from "framer-motion";
import { Badge } from "@/components/ui/badge";

const roadmapAgents = [
  {
    icon: "🧠",
    title: "Tactician — Decision Engine",
    body: "Evaluates remediation options, weighs risk vs. impact, and determines whether human approval is required before acting.",
  },
  {
    icon: "🤝",
    title: "Diplomat — Approval Gate",
    body: "Manages human-in-the-loop approvals via Slack or email. Handles escalation paths when automated remediation is blocked.",
  },
];

const RoadmapSection = () => {
  return (
    <section className="py-24 relative">
      <div className="container mx-auto px-4">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center mb-16"
        >
          <h2 className="text-3xl sm:text-4xl font-bold text-foreground mb-4">What's Next</h2>
          <p className="text-muted-foreground max-w-xl mx-auto">
            Four agents are live. The rest of the swarm is on the way.
          </p>
        </motion.div>

        <div className="grid md:grid-cols-2 gap-6 max-w-2xl mx-auto">
          {roadmapAgents.map((agent, i) => (
            <motion.div
              key={agent.title}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5, delay: i * 0.15 }}
              whileHover={{ y: -6 }}
              className="relative rounded-lg border border-dashed border-warning/40 bg-card p-6 flex flex-col gap-4 transition-all opacity-80"
            >
              <Badge className="absolute top-3 right-3 bg-warning/15 text-warning border-warning/30 text-[10px]">
                COMING SOON
              </Badge>
              <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
                <span className="text-2xl">{agent.icon}</span>
                {agent.title}
              </h3>
              <p className="text-sm text-muted-foreground leading-relaxed">{agent.body}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default RoadmapSection;
