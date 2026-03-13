import { useState } from "react";
import { ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth";

export function LoginPage() {
  const [key, setKey] = useState("");
  const [error, setError] = useState("");
  const { login } = useAuth();

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = key.trim();
    if (!trimmed.startsWith("cai_")) {
      setError("API key must start with cai_");
      return;
    }
    if (trimmed.length < 10) {
      setError("API key is too short");
      return;
    }
    setError("");
    login(trimmed);
  }

  return (
    <div className="noise-overlay flex min-h-screen items-center justify-center bg-background">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex flex-col items-center gap-3">
          <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-teal/20 ring-1 ring-teal/40">
            <ShieldAlert className="h-7 w-7 text-teal-light" />
          </div>
          <h1 className="font-heading text-2xl font-extrabold tracking-tight text-foreground">
            Calseta
          </h1>
          <p className="text-sm text-muted-foreground">
            Connect with your API key to access the admin panel
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Input
              type="password"
              placeholder="cai_..."
              value={key}
              onChange={(e) => setKey(e.target.value)}
              className="h-11 bg-card border-border text-foreground placeholder:text-dim font-mono"
              autoFocus
            />
            {error && (
              <p className="text-xs text-red-threat">{error}</p>
            )}
          </div>
          <Button
            type="submit"
            className="w-full h-11 bg-teal text-white hover:bg-teal-dim font-medium"
          >
            Connect
          </Button>
        </form>

        <p className="text-center text-xs text-dim">
          Your key is stored locally and never sent to any third party.
        </p>
      </div>
    </div>
  );
}
