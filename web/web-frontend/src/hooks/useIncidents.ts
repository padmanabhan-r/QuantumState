import { useQuery } from "@tanstack/react-query";
import { fetchIncidents, fetchIncidentStats } from "@/lib/api";

export function useIncidents() {
  return useQuery({
    queryKey: ["incidents"],
    queryFn: fetchIncidents,
    refetchInterval: 10_000,
  });
}

export function useIncidentStats() {
  return useQuery({
    queryKey: ["incident-stats"],
    queryFn: fetchIncidentStats,
    refetchInterval: 30_000,
  });
}
