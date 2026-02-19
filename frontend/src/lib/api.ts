const API_BASE = import.meta.env.VITE_API_BASE_URL
  ? `${import.meta.env.VITE_API_BASE_URL}/api`
  : "/api";

export interface Incident {
  id: string;
  "@timestamp": string;
  service: string;
  anomaly_type: string;
  resolution_status: "RESOLVED" | "MONITORING" | "ESCALATE" | "PARTIALLY_RESOLVED" | string;
  mttr_estimate: string;
  root_cause: string;
  action_taken: string;
  pipeline_summary: string;
}

export interface IncidentsResponse {
  incidents: Incident[];
  total: number;
  error?: string;
}

export interface IncidentStats {
  incidents_today: number;
  resolved_today: number;
  avg_mttr_seconds: number;
  manual_baseline_seconds: number;
  error?: string;
}

export interface ServiceHealth {
  service: string;
  cpu_percent: number | null;
  memory_percent: number | null;
  error_rate: number | null;
  latency_ms: number | null;
}

export interface HealthResponse {
  services: ServiceHealth[];
  error?: string;
}

export interface ChatResponse {
  response?: string;
  error?: string;
  agent: string;
}

export async function fetchIncidents(credHeaders: Record<string, string> = {}): Promise<IncidentsResponse> {
  const res = await fetch(`${API_BASE}/incidents`, { headers: credHeaders });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function fetchIncidentStats(credHeaders: Record<string, string> = {}): Promise<IncidentStats> {
  const res = await fetch(`${API_BASE}/incidents/stats`, { headers: credHeaders });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function fetchHealth(credHeaders: Record<string, string> = {}): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/health`, { headers: credHeaders });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function sendChat(
  agentId: string,
  message: string,
  credHeaders: Record<string, string> = {}
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...credHeaders },
    body: JSON.stringify({ agent_id: agentId, message }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
