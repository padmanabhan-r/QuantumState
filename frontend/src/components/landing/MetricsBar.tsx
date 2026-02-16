import { useEffect, useRef, useState } from "react";
import { motion, useInView } from "framer-motion";

const metrics = [
  { label: "MTTR reduction", value: 91, suffix: "%" },
  { label: "Live agents", value: 4, suffix: "" },
  { label: "Elastic indices monitored", value: 5, suffix: "" },
  { label: "Pipeline latency", value: 5, suffix: " min", prefix: "< " },
];

const CountUp = ({ target, suffix = "", prefix = "" }: { target: number; suffix?: string; prefix?: string }) => {
  const [count, setCount] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });

  useEffect(() => {
    if (!inView) return;
    let start = 0;
    const duration = 1500;
    const step = Math.ceil(target / (duration / 16));
    const timer = setInterval(() => {
      start += step;
      if (start >= target) {
        setCount(target);
        clearInterval(timer);
      } else {
        setCount(start);
      }
    }, 16);
    return () => clearInterval(timer);
  }, [inView, target]);

  return (
    <span ref={ref} className="text-4xl sm:text-5xl font-bold text-gradient-blue font-mono">
      {prefix}{count}{suffix}
    </span>
  );
};

const MetricsBar = () => {
  return (
    <section className="py-16 border-y border-border bg-muted/20">
      <div className="container mx-auto px-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
          {metrics.map((m, i) => (
            <motion.div
              key={m.label}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1 }}
              className="text-center"
            >
              <CountUp target={m.value} suffix={m.suffix} prefix={m.prefix} />
              <p className="text-sm text-muted-foreground mt-2">{m.label}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default MetricsBar;
