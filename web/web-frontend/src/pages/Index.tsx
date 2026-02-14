import Navbar from "@/components/landing/Navbar";
import HeroSection from "@/components/landing/HeroSection";
import WhatIsSection from "@/components/landing/WhatIsSection";
import HowItWorksSection from "@/components/landing/HowItWorksSection";
import MetricsBar from "@/components/landing/MetricsBar";
import ArchitectureSection from "@/components/landing/ArchitectureSection";
import RoadmapSection from "@/components/landing/RoadmapSection";
import CtaBanner from "@/components/landing/CtaBanner";
import Footer from "@/components/landing/Footer";

const Index = () => {
  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <HeroSection />
      <WhatIsSection />
      <HowItWorksSection />
      <MetricsBar />
      <ArchitectureSection />
      <RoadmapSection />
      <CtaBanner />
      <Footer />
    </div>
  );
};

export default Index;
