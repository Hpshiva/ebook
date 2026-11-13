import { useState, type FormEvent } from "react";
import { useAction } from "../hooks/useLoad";
import { api } from "../services/api";
import type { Settings } from "../types";
import { Badge, Button, Card, ErrorNote, Field, Input, Notice } from "./ui";

type Saved = Settings & { apify_limits?: { remaining_usd: number } | null };

/** Admin-only box to save the Apify token inside the app. The token is never shown again. */
export function ApifyToken({ settings, onChange }: { settings: Settings; onChange: (s: Settings) => void }) {
  const [token, setToken] = useState("");
  const [note, setNote] = useState("");
  const action = useAction();
  const fromEnv = settings.apify_token_source === "server environment";

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setNote("");
    const out = await action.run(() => api.put<Saved>("/api/settings/apify-token", { token }));
    if (out) {
      setToken("");
      onChange(out);
      setNote(out.apify_limits ? `Token saved. Apify free allowance left this month: $${out.apify_limits.remaining_usd}.` : "Token saved.");
    }
  };

  const clear = async () => {
    if (!window.confirm("Take the saved Apify token out of the app? Live searches will stop working.")) return;
    const out = await action.run(() => api.del<Settings>("/api/settings/apify-token"));
    if (out) {
      onChange(out);
      setNote("Token cleared.");
    }
  };

  return (
    <Card title="Apify token (for real Instagram data)"
      action={<Badge tone={settings.apify_token_configured ? "green" : "amber"}>{settings.apify_token_configured ? "Configured" : "Not configured"}</Badge>}>
      <p className="mb-3 text-sm text-slate-600">
        {settings.apify_token_configured
          ? `A token is ${settings.apify_token_source ?? "configured"}. It is never shown again.`
          : "Paste your token from Apify → Settings → API & Integrations. It is checked with Apify, stored privately and never shown again."}
      </p>
      {fromEnv ? (
        <p className="text-xs text-slate-500">To change it, edit APIFY_TOKEN in the server environment.</p>
      ) : (
        <form onSubmit={save} className="flex flex-wrap items-end gap-2">
          <div className="min-w-64 flex-1">
            <Field label={settings.apify_token_configured ? "Replace token" : "Apify API token"}>
              <Input aria-label="Apify API token" type="password" autoComplete="off" placeholder="apify_api_…" value={token}
                onChange={(e) => setToken(e.target.value)} />
            </Field>
          </div>
          <Button type="submit" disabled={action.busy || token.trim().length < 20}>{action.busy ? "Checking…" : "Save token"}</Button>
          {settings.apify_token_configured && <Button variant="danger" disabled={action.busy} onClick={clear}>Clear token</Button>}
        </form>
      )}
      <div className="mt-3 space-y-2">
        <ErrorNote error={action.error} />
        {note && <Notice tone="success">{note}</Notice>}
      </div>
    </Card>
  );
}
