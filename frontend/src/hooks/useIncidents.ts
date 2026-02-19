import { useQuery } from "@tanstack/react-query";
import { fetchIncidents, fetchIncidentStats } from "@/lib/api";
import { useCredentials } from "@/contexts/CredentialsContext";

export function useIncidents() {
  const { credHeaders } = useCredentials();
  return useQuery({
    queryKey: ["incidents", credHeaders],
    queryFn: () => fetchIncidents(credHeaders),
    refetchInterval: 10_000,
  });
}

export function useIncidentStats() {
  const { credHeaders } = useCredentials();
  return useQuery({
    queryKey: ["incident-stats", credHeaders],
    queryFn: () => fetchIncidentStats(credHeaders),
    refetchInterval: 30_000,
  });
}
