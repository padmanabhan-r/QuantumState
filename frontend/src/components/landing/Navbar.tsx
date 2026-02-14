import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Menu, X, Zap } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import ElasticIcon from "@/components/ElasticIcon";

const Navbar = () => {
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", handler);
    return () => window.removeEventListener("scroll", handler);
  }, []);

  return (
    <nav
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled ? "bg-background/80 backdrop-blur-xl border-b border-border" : "bg-transparent"
      }`}
    >
      <div className="container mx-auto flex items-center justify-between h-16 px-4">
        <Link to="/" className="flex items-center gap-1.5">
          <Zap className="h-5 w-5 text-secondary fill-secondary" />
          <span className="text-xl font-bold text-gradient-blue">QuantumState</span>
          <span className="hidden sm:inline-flex ml-2 items-center gap-1.5 px-2 py-0.5 text-[10px] font-mono rounded-full border border-border text-muted-foreground">
            Powered by <ElasticIcon size={13} /> Elastic Agent Builder
          </span>
        </Link>

        <Button
          onClick={() => navigate("/console")}
          className="hidden md:inline-flex rounded-full bg-gradient-blue text-primary-foreground hover:opacity-90 transition-opacity"
        >
          Open Console →
        </Button>

        <button
          className="md:hidden text-foreground"
          onClick={() => setMobileOpen(!mobileOpen)}
        >
          {mobileOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>

      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="md:hidden bg-background/95 backdrop-blur-xl border-b border-border"
          >
            <div className="p-4">
              <Button
                onClick={() => {
                  navigate("/console");
                  setMobileOpen(false);
                }}
                className="w-full rounded-full bg-gradient-blue text-primary-foreground"
              >
                Open Console →
              </Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </nav>
  );
};

export default Navbar;
