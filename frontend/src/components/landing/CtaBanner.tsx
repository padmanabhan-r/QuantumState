import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ArrowRight } from "lucide-react";
import { motion } from "framer-motion";

const CtaBanner = () => {
  const navigate = useNavigate();

  return (
    <section className="py-24 relative overflow-hidden">
      <div className="absolute inset-0 bg-gradient-cta" />
      <div className="absolute inset-0 hero-grid-bg opacity-30" />

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        className="container mx-auto px-4 text-center relative z-10"
      >
        <h2 className="text-3xl sm:text-4xl font-bold text-foreground mb-4">See it in action</h2>
        <p className="text-muted-foreground max-w-xl mx-auto mb-8">
          Open the live SRE console. Watch Cassandra detect an anomaly, Archaeologist trace the root cause,
          and Surgeon resolve it — in real time.
        </p>
        <Button
          size="lg"
          className="rounded-full bg-gradient-blue text-primary-foreground hover:opacity-90 transition-opacity px-8 text-base"
          onClick={() => navigate("/console")}
        >
          Open SRE Console <ArrowRight className="ml-2 h-4 w-4" />
        </Button>
      </motion.div>
    </section>
  );
};

export default CtaBanner;
