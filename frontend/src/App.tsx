import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Index from "./pages/Index";
import Console from "./pages/Console";
import SimControl from "./pages/SimControl";
import NotFound from "./pages/NotFound";
import { CredentialsProvider } from "./contexts/CredentialsContext";

const queryClient = new QueryClient();

const App = () => (
  <CredentialsProvider>
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Index />} />
          <Route path="/console" element={<Console />} />
          <Route path="/sim" element={<SimControl />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
  </CredentialsProvider>
);

export default App;
