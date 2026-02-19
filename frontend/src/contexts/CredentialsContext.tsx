import { createContext, useContext, useState, ReactNode } from "react";

interface CustomCreds {
  cloudId: string;
  apiKey: string;
  kibanaUrl: string;
}

interface CredentialsContextValue {
  isCustom: boolean;
  creds: CustomCreds;
  setCreds: (c: CustomCreds) => void;
  resetCreds: () => void;
  credHeaders: Record<string, string>;
}

const empty: CustomCreds = { cloudId: "", apiKey: "", kibanaUrl: "" };

const CredentialsContext = createContext<CredentialsContextValue>({
  isCustom: false,
  creds: empty,
  setCreds: () => {},
  resetCreds: () => {},
  credHeaders: {},
});

export function CredentialsProvider({ children }: { children: ReactNode }) {
  const [creds, setCredsState] = useState<CustomCreds>(empty);

  const isCustom = !!(creds.cloudId || creds.apiKey || creds.kibanaUrl);

  const credHeaders: Record<string, string> = isCustom
    ? {
        ...(creds.cloudId  && { "X-Elastic-Cloud-Id": creds.cloudId }),
        ...(creds.apiKey   && { "X-Elastic-Api-Key":  creds.apiKey }),
        ...(creds.kibanaUrl && { "X-Kibana-Url":      creds.kibanaUrl }),
      }
    : {};

  function setCreds(c: CustomCreds) {
    setCredsState(c);
  }

  function resetCreds() {
    setCredsState(empty);
  }

  return (
    <CredentialsContext.Provider value={{ isCustom, creds, setCreds, resetCreds, credHeaders }}>
      {children}
    </CredentialsContext.Provider>
  );
}

export function useCredentials() {
  return useContext(CredentialsContext);
}
