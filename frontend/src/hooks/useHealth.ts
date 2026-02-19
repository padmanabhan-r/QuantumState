import { useQuery } from "@tanstack/react-query";
import { fetchHealth } from "@/lib/api";
import { useCredentials } from "@/contexts/CredentialsContext";

export function useHealth() {
  const { credHeaders } = useCredentials();
  return useQuery({
    queryKey: ["health", credHeaders],
    queryFn: () => fetchHealth(credHeaders),
    refetchInterval: 15_000,
  });
}
