import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ArrowRight, TrendingDown, Sparkles } from "lucide-react";
import ElasticIcon from "@/components/ElasticIcon";
import { motion } from "framer-motion";

const HeroSection = () => {
  const navigate = useNavigate();

  return (
    <section className="relative min-h-screen flex items-center justify-center hero-grid-bg overflow-hidden">
      {/* Radial glow */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[400px] rounded-full bg-primary/5 blur-[120px]" />
      </div>

      <div className="container mx-auto px-4 pt-24 pb-16 relative z-10">
        <div className="max-w-4xl mx-auto text-center">
          <motion.h1
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7 }}
            className="text-5xl sm:text-6xl lg:text-7xl font-bold leading-tight mb-6"
          >
            <span className="text-gradient-blue animate-shimmer bg-[linear-gradient(110deg,hsl(var(--primary)),hsl(var(--secondary)),hsl(var(--primary)))]">
              Autonomous SRE.
            </span>
            <br />
            <span className="text-foreground">Predict. Investigate. Resolve.</span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.2 }}
            className="text-lg sm:text-xl text-muted-foreground max-w-2xl mx-auto mb-10"
          >
            QuantumState is a swarm of AI agents that detects production anomalies,
            traces root causes, and executes remediations — before your on-call engineer even gets paged.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.4 }}
            className="flex flex-col sm:flex-row gap-4 justify-center mb-14"
          >
            <Button
              size="lg"
              className="rounded-full bg-gradient-blue text-primary-foreground hover:opacity-90 transition-opacity px-8 text-base"
              onClick={() => navigate("/console")}
            >
              Open SRE Console <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
            <Button
              size="lg"
              variant="outline"
              className="rounded-full border-border text-foreground hover:bg-muted px-8 text-base"
              asChild
            >
              <a href="#">View on GitHub</a>
            </Button>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.6 }}
            className="flex flex-wrap justify-center gap-4"
          >
            <StatChip icon={<TrendingDown className="h-4 w-4 text-success" />} label="47 min → ~4 min MTTR" accent="success" />
            <StatChip icon={<Sparkles className="h-4 w-4 text-primary" />} label="3 AI Agents — Live Now" accent="primary" />
            <StatChip icon={<ElasticIcon size={16} />} label="Elastic Agent Builder" accent="warning" />
          </motion.div>
        </div>
      </div>
    </section>
  );
};

const StatChip = ({
  icon,
  label,
}: {
  icon: React.ReactNode;
  label: string;
  accent: string;
}) => (
  <div className="flex items-center gap-2 px-4 py-2 rounded-full border border-border bg-muted/50 text-sm font-mono text-foreground">
    {icon}
    {label}
  </div>
);

export default HeroSection;
