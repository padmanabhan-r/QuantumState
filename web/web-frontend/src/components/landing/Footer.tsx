import { Link } from "react-router-dom";
import { Zap } from "lucide-react";
import ElasticIcon from "@/components/ElasticIcon";

const Footer = () => {
  return (
    <footer className="border-t border-border py-8">
      <div className="container mx-auto px-4 flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-muted-foreground">
        <div className="flex items-center gap-1.5">
          <Zap className="h-4 w-4 text-secondary fill-secondary" />
          <span className="text-gradient-blue font-semibold">QuantumState</span>
          <span>© 2026</span>
        </div>

        <span className="font-mono text-xs flex items-center gap-1.5">
          Powered by <ElasticIcon size={14} /> Elastic Agent Builder
        </span>

        <div className="flex gap-4">
          <Link to="/sim" className="hover:text-foreground transition-colors">Simulation Control</Link>
          <a href="https://github.com/padmanabhan-r/QuantumState" target="_blank" rel="noopener noreferrer" className="hover:text-foreground transition-colors">GitHub</a>
          <Link to="/console" className="hover:text-foreground transition-colors">Console</Link>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
