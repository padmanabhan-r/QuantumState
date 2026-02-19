import { useState, useEffect } from "react";
import { KeyRound, X, RotateCcw, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { useCredentials } from "@/contexts/CredentialsContext";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function CredentialsModal({ open, onClose }: Props) {
  const { creds, setCreds, resetCreds, isCustom } = useCredentials();

  const [cloudId,   setCloudId]   = useState(creds.cloudId);
  const [apiKey,    setApiKey]    = useState(creds.apiKey);
  const [kibanaUrl, setKibanaUrl] = useState(creds.kibanaUrl);

  // Sync local state when modal opens
  useEffect(() => {
    if (open) {
      setCloudId(creds.cloudId);
      setApiKey(creds.apiKey);
      setKibanaUrl(creds.kibanaUrl);
    }
  }, [open]);

  function handleApply() {
    setCreds({ cloudId: cloudId.trim(), apiKey: apiKey.trim(), kibanaUrl: kibanaUrl.trim() });
    onClose();
  }

  function handleReset() {
    resetCreds();
    setCloudId("");
    setApiKey("");
    setKibanaUrl("");
    onClose();
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-primary" />
            Your Elastic Credentials
          </DialogTitle>
          <DialogDescription>
            Override the default cluster for this session. Credentials are never stored — they live only in this browser tab.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4 py-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="cloud-id" className="text-xs text-muted-foreground">
              Elastic Cloud ID
            </Label>
            <Input
              id="cloud-id"
              placeholder="my-cluster:dXMtZWFzdC0xLmF3cy5mb..."
              value={cloudId}
              onChange={(e) => setCloudId(e.target.value)}
              className="font-mono text-xs"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="api-key" className="text-xs text-muted-foreground">
              API Key
            </Label>
            <Input
              id="api-key"
              type="password"
              placeholder="your-api-key-here"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              className="font-mono text-xs"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="kibana-url" className="text-xs text-muted-foreground">
              Kibana URL <span className="text-muted-foreground/50">(optional — derived from Cloud ID if omitted)</span>
            </Label>
            <Input
              id="kibana-url"
              placeholder="https://my-cluster.kb.us-east-1.aws.found.io"
              value={kibanaUrl}
              onChange={(e) => setKibanaUrl(e.target.value)}
              className="font-mono text-xs"
            />
            <p className="text-[11px] text-muted-foreground">
              Only needed if your Kibana URL cannot be derived from the Cloud ID above.
            </p>
          </div>
        </div>

        <div className="flex gap-2 pt-2">
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5 text-muted-foreground"
            onClick={handleReset}
            disabled={!isCustom && !cloudId && !apiKey && !kibanaUrl}
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Reset to default
          </Button>
          <Button size="sm" className="ml-auto gap-1.5" onClick={handleApply}>
            <Check className="h-3.5 w-3.5" />
            Apply
          </Button>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
