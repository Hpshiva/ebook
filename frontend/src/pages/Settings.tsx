import { useEffect, useState, type FormEvent } from "react";
import { Badge, Button, Card, Checkbox, ErrorNote, Field, Input, Notice, PageHeader, Select, Spinner, Table, Td } from "../components/ui";
import { ApifyToken } from "../components/ApifyToken";
import { useAuth } from "../hooks/useAuth";
import { useAction, useLoad } from "../hooks/useLoad";
import { api } from "../services/api";
import type { Client, Settings as S, User } from "../types";
import { dateTime, label } from "../utils/format";

function Users() {
  const users = useLoad(() => api.get<User[]>("/api/users"));
  const clients = useLoad(() => api.get<Client[]>("/api/clients"));
  const [form, setForm] = useState({ email: "", name: "", password: "", role: "staff", client_id: "" });
  const action = useAction();
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const ok = await action.run(() => api.post("/api/users", { ...form, client_id: form.client_id ? Number(form.client_id) : null }));
    if (ok) { setForm({ email: "", name: "", password: "", role: "staff", client_id: "" }); void users.reload(); }
  };
  const toggle = async (u: User) => { if (await action.run(() => api.patch(`/api/users/${u.id}`, { is_active: !u.is_active }))) void users.reload(); };

  return (
    <Card title="Users and access">
      <Table head={["Name", "Email", "Role", "Status", ""]}>
        {(users.data ?? []).map((u) => (
          <tr key={u.id}>
            <Td>{u.name}</Td><Td>{u.email}</Td>
            <Td><Badge tone={u.role === "admin" ? "indigo" : u.role === "client" ? "amber" : "slate"}>{u.role}</Badge></Td>
            <Td>{u.is_active ? "Active" : "Deactivated"}</Td>
            <Td><Button small variant="secondary" disabled={action.busy} onClick={() => toggle(u)}>{u.is_active ? "Deactivate" : "Activate"}</Button></Td>
          </tr>
        ))}
      </Table>
      <form onSubmit={submit} className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
        <Input aria-label="New user name" placeholder="Name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <Input aria-label="New user email" type="email" placeholder="Email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        <Input aria-label="New user password" type="password" placeholder="Password (8+ characters)" required minLength={8} autoComplete="new-password"
          value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        <Select aria-label="Role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}
          options={[{ value: "staff", label: "Staff" }, { value: "admin", label: "Admin" }, { value: "client", label: "Client (portal only)" }]} />
        {form.role === "client" && (
          <Select aria-label="Client" required value={form.client_id} onChange={(e) => setForm({ ...form, client_id: e.target.value })} placeholder="Which client?"
            options={(clients.data ?? []).map((c) => ({ value: c.id, label: c.name }))} />
        )}
        <Button type="submit" disabled={action.busy}>Add user</Button>
      </form>
      <div className="mt-3"><ErrorNote error={action.error || users.error} /></div>
    </Card>
  );
}

export function Settings() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const loaded = useLoad(() => api.get<S>("/api/settings"));
  const [s, setS] = useState<S | null>(null);
  const [saved, setSaved] = useState("");
  const action = useAction();
  useEffect(() => { if (loaded.data) setS(loaded.data); }, [loaded.data]);

  if (!s) return loaded.error ? <ErrorNote error={loaded.error} /> : <Spinner />;
  const weightTotal = Object.values(s.scoring_weights).reduce((a, b) => a + Number(b || 0), 0);

  const save = async () => {
    setSaved("");
    const { apify_token_configured: _a, apify_token_source: _b, apify_pricing: _p, fx, ...rest } = s;
    const out = await action.run(() => api.put<S>("/api/settings", { ...rest, fx: { usd_inr: Number(fx.usd_inr) } }));
    if (out) { setS(out); setSaved("Settings saved. New searches and re-analysis use them."); }
  };
  const numField = (text: string, value: number, onChange: (v: number) => void, hint?: string) => (
    <Field label={text} hint={hint}><Input type="number" min={0} aria-label={text} disabled={!isAdmin} value={value} onChange={(e) => onChange(Number(e.target.value))} /></Field>
  );

  return (
    <>
      <PageHeader title="Settings" subtitle={isAdmin ? "Defaults for every search, scoring and cost protection." : "Only an administrator can change these."}
        action={isAdmin && <Button disabled={action.busy} onClick={save}>{action.busy ? "Saving…" : "Save settings"}</Button>} />
      <div className="mb-4 space-y-2"><ErrorNote error={action.error} />{saved && <Notice tone="success">{saved}</Notice>}</div>
      <div className="space-y-5">
        <Card title="Cost protection">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {numField("Monthly cash budget (₹)", s.monthly_budget_inr, (v) => setS({ ...s, monthly_budget_inr: v }), "₹0 means never spend beyond free allowances.")}
            {numField("Warn at % of budget", s.budget_warn_pct, (v) => setS({ ...s, budget_warn_pct: v }))}
            {numField("Max profiles per search", s.max_profiles_per_search, (v) => setS({ ...s, max_profiles_per_search: v }))}
            {numField("Cache profiles for (days)", s.cache_days, (v) => setS({ ...s, cache_days: v }), "Cached profiles are not collected again.")}
            {numField("Reels checked per creator", s.reels_per_creator, (v) => setS({ ...s, reels_per_creator: v }), "Live mode only. Each reel is charged by the provider.")}
            <Field label="USD to INR rate" hint={`${s.fx.source}${s.fx.updated_at ? `, ${dateTime(s.fx.updated_at)}` : ""}`}>
              <Input type="number" step="0.01" min={1} aria-label="USD to INR rate" disabled={!isAdmin} value={s.fx.usd_inr} onChange={(e) => setS({ ...s, fx: { ...s.fx, usd_inr: Number(e.target.value) } })} />
            </Field>
            <Field label="Sender name for outreach"><Input aria-label="Sender name" disabled={!isAdmin} value={s.sender_name} onChange={(e) => setS({ ...s, sender_name: e.target.value })} /></Field>
          </div>
          <div className="mt-4 space-y-2">
            <Checkbox label="Also collect public phone numbers" disabled={!isAdmin} checked={s.collect_phone} onChange={(v) => setS({ ...s, collect_phone: v })} />
            {!s.apify_token_configured && <Notice tone="error">No Apify token is saved, so searches cannot collect real data yet. Add it below.</Notice>}
          </div>
        </Card>

        {isAdmin && (
          <ApifyToken settings={s} onChange={(out) => setS((cur) => (cur
            ? { ...cur, apify_token_configured: out.apify_token_configured, apify_token_source: out.apify_token_source } : cur))} />
        )}

        <Card title="Default filters">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {numField("Min followers", s.filters.min_followers, (v) => setS({ ...s, filters: { ...s.filters, min_followers: v } }))}
            {numField("Max followers", s.filters.max_followers, (v) => setS({ ...s, filters: { ...s.filters, max_followers: v } }))}
            {numField("Min median reel views", s.filters.min_views, (v) => setS({ ...s, filters: { ...s.filters, min_views: v } }))}
            {numField("Max median reel views", s.filters.max_views, (v) => setS({ ...s, filters: { ...s.filters, max_views: v } }))}
            {numField("Min reels with views", s.filters.min_reels, (v) => setS({ ...s, filters: { ...s.filters, min_reels: v } }))}
          </div>
          <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2">
            <Checkbox label="Require a public email" disabled={!isAdmin} checked={s.filters.require_email} onChange={(v) => setS({ ...s, filters: { ...s.filters, require_email: v } })} />
            <Checkbox label="No email: send to Needs review (contact by DM)" disabled={!isAdmin || !s.filters.require_email}
              checked={s.filters.require_email && s.filters.no_email_to_review} onChange={(v) => setS({ ...s, filters: { ...s.filters, no_email_to_review: v } })} />
            <Checkbox label="Exclude creators already selling" disabled={!isAdmin} checked={s.filters.exclude_selling} onChange={(v) => setS({ ...s, filters: { ...s.filters, exclude_selling: v } })} />
            <Checkbox label="Public profiles only" disabled={!isAdmin} checked={s.filters.require_public} onChange={(v) => setS({ ...s, filters: { ...s.filters, require_public: v } })} />
          </div>
        </Card>

        <Card title="Lead score weights" action={<Badge tone={weightTotal === 100 ? "green" : "amber"}>Total: {weightTotal}</Badge>}>
          <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
            {Object.entries(s.scoring_weights).map(([key, value]) => (
              <div key={key}>{numField(label(key), value, (v) => setS({ ...s, scoring_weights: { ...s.scoring_weights, [key]: v } }))}</div>
            ))}
          </div>
          <p className="mt-3 text-xs text-slate-500">Scores are scaled to 100 whatever the total. Criteria with no data are left out rather than scored as zero.</p>
        </Card>

        {isAdmin && <Users />}
      </div>
    </>
  );
}
