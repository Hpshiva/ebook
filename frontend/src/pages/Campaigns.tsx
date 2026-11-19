import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { ExportButtons } from "../components/shared";
import { Badge, Button, Card, Empty, ErrorNote, Field, Input, Modal, Notice, PageHeader, ScorePill, Select, SellingBadge, SkeletonRows, Spinner, Stat, Table, Td } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { useAction, useLoad } from "../hooks/useLoad";
import { api } from "../services/api";
import type { Campaign, CampaignDetail as Detail, CampaignLink, Client } from "../types";
import { compact, day } from "../utils/format";

const EMPTY = { name: "", client_id: "", niche: "", product_name: "", target_leads: "0", status: "Active" };

function CampaignForm({ initial, clients, onClose, onSaved }: { initial?: Campaign; clients: Client[]; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState(initial ? {
    name: initial.name, client_id: String(initial.client_id ?? ""), niche: initial.niche, product_name: initial.product_name,
    target_leads: String(initial.target_leads), status: initial.status,
  } : EMPTY);
  const action = useAction();
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const body = { ...form, client_id: form.client_id ? Number(form.client_id) : null, target_leads: Number(form.target_leads) || 0 };
    const ok = await action.run(() => (initial ? api.patch(`/api/campaigns/${initial.id}`, body) : api.post("/api/campaigns", body)));
    if (ok) { onSaved(); onClose(); }
  };
  return (
    <Modal title={initial ? "Edit campaign" : "New campaign"} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <Field label="Campaign name"><Input aria-label="Campaign name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
        <Field label="Client" hint="Leave empty for our own partnership campaign.">
          <Select aria-label="Client" value={form.client_id} onChange={(e) => setForm({ ...form, client_id: e.target.value })} placeholder="Our own campaign"
            options={clients.map((c) => ({ value: c.id, label: c.name }))} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Niche"><Input value={form.niche} onChange={(e) => setForm({ ...form, niche: e.target.value })} /></Field>
          <Field label="Target leads"><Input type="number" min={0} value={form.target_leads} onChange={(e) => setForm({ ...form, target_leads: e.target.value })} /></Field>
        </div>
        <Field label="Product"><Input value={form.product_name} onChange={(e) => setForm({ ...form, product_name: e.target.value })} placeholder="e.g. Fitness PDF guide" /></Field>
        <Field label="Status"><Select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} options={["Active", "Paused", "Completed"]} /></Field>
        <ErrorNote error={action.error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={action.busy}>{action.busy ? "Saving…" : "Save campaign"}</Button>
        </div>
      </form>
    </Modal>
  );
}

export function Campaigns() {
  const { user } = useAuth();
  const isClient = user?.role === "client";
  const list = useLoad(() => api.get<Campaign[]>("/api/campaigns"));
  const clients = useLoad(() => (isClient ? Promise.resolve([] as Client[]) : api.get<Client[]>("/api/clients")), [isClient]);
  const [creating, setCreating] = useState(false);

  return (
    <>
      <PageHeader title={isClient ? "My Campaigns" : "Campaigns"}
        subtitle={isClient ? "Creator shortlists prepared for you." : "Client projects and our own partnership campaigns."}
        action={!isClient && <Button onClick={() => setCreating(true)}>New campaign</Button>} />
      <ErrorNote error={list.error} />
      {list.loading && !list.data ? <SkeletonRows /> : !list.data?.length ? (
        <Empty title="No campaigns yet" text={isClient ? "Your shortlists will appear here." : "Create a campaign to group creators for a client or for our own products."}
          action={!isClient && <Button onClick={() => setCreating(true)}>New campaign</Button>} />
      ) : (
        <Table head={["Campaign", "Type", "Niche", isClient ? "Leads" : "Creators", "Shortlisted", "Approved", "Status", "Created"]}>
          {list.data.map((c) => (
            <tr key={c.id} className="hover:bg-slate-50">
              <Td><Link to={`/campaigns/${c.id}`} className="font-medium text-slate-900 hover:text-indigo-700">{c.name}</Link>
                {c.product_name && <p className="text-xs text-slate-500">{c.product_name}</p>}</Td>
              <Td>{c.type === "own" ? <Badge tone="indigo">Our own</Badge> : <Badge>{c.client_name}</Badge>}</Td>
              <Td>{c.niche || "—"}</Td>
              <Td className="tabular-nums">{c.creators}{c.target_leads ? ` / ${c.target_leads}` : ""}</Td>
              <Td className="tabular-nums">{c.shortlisted}</Td>
              <Td className="tabular-nums">{c.approved}</Td>
              <Td>{c.status}</Td>
              <Td className="text-xs text-slate-500">{day(c.created_at)}</Td>
            </tr>
          ))}
        </Table>
      )}
      {creating && <CampaignForm clients={clients.data ?? []} onClose={() => setCreating(false)} onSaved={list.reload} />}
    </>
  );
}

export function CampaignDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const isClient = user?.role === "client";
  const { data: c, loading, error, reload } = useLoad(() => api.get<Detail>(`/api/campaigns/${id}`), [id]);
  const clients = useLoad(() => (isClient ? Promise.resolve([] as Client[]) : api.get<Client[]>("/api/clients")), [isClient]);
  const [editing, setEditing] = useState(false);
  const action = useAction();

  if (loading && !c) return <Spinner />;
  if (!c) return <ErrorNote error={error || "Campaign not found"} />;

  const act = async (fn: () => Promise<unknown>) => { if ((await action.run(fn)) !== undefined) void reload(); };
  const decide = (l: CampaignLink, approval: string) => act(() => api.post(`/api/campaigns/${c.id}/creators/${l.id}/decision`, { approval }));

  return (
    <>
      <PageHeader title={c.name}
        subtitle={`${c.type === "own" ? "Our own partnership campaign" : `Client: ${c.client_name}`}${c.niche ? ` · ${c.niche}` : ""}${c.product_name ? ` · ${c.product_name}` : ""}`}
        action={<>
          <ExportButtons params={{ scope: "campaign", campaign_id: c.id }} disabled={c.links.length === 0} />
          {!isClient && <Button small variant="secondary" onClick={() => setEditing(true)}>Edit</Button>}
        </>} />
      <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label={isClient ? "Leads shared" : "Creators"} value={c.links.length} hint={c.target_leads ? `Target: ${c.target_leads}` : undefined} />
        <Stat label="Shortlisted" value={c.shortlisted} />
        <Stat label="Approved" value={c.approved} tone="green" />
        <Stat label="Rejected" value={c.rejected} tone="red" />
      </div>
      <div className="mb-3 space-y-2">
        <ErrorNote error={action.error} />
        {!isClient && <Notice>Clients only see creators you shortlist. Add creators from Discover or the Creator Database.</Notice>}
      </div>
      {c.links.length === 0 ? <Empty title="No creators in this campaign yet" text={isClient ? "Leads will appear here once they are shortlisted for you." : "Select creators on the Discover or Creator Database page and add them here."} /> : (
        <Card>
          <div className="-m-4">
            <Table head={["Creator", "Followers", "Reel views", "Score", "Selling", "Email", ...(isClient ? [] : ["Shortlist"]), "Approval", ""]}>
              {c.links.map((l) => (
                <tr key={l.id}>
                  <Td>
                    {isClient
                      ? <a href={l.creator.profile_url} target="_blank" rel="noreferrer noopener" className="font-medium text-slate-900 hover:text-indigo-700">@{l.creator.username}</a>
                      : <Link to={`/creators/${l.creator.id}`} className="font-medium text-slate-900 hover:text-indigo-700">@{l.creator.username}</Link>}
                    <div className="flex items-center gap-1 text-xs text-slate-500">{l.creator.full_name}</div>
                  </Td>
                  <Td className="tabular-nums">{compact(l.creator.followers)}</Td>
                  <Td className="tabular-nums">{compact(l.creator.median_reel_views)}</Td>
                  <Td><ScorePill score={l.creator.lead_score} confidence={l.creator.confidence} /></Td>
                  <Td><SellingBadge status={l.creator.selling_status} /></Td>
                  <Td className="text-xs">{l.creator.email ?? "—"}</Td>
                  {!isClient && (
                    <Td><Button small variant={l.shortlisted ? "secondary" : "primary"} disabled={action.busy}
                      onClick={() => act(() => api.patch(`/api/campaigns/${c.id}/creators/${l.id}`, { shortlisted: !l.shortlisted }))}>
                      {l.shortlisted ? "Shortlisted ✓" : "Shortlist"}</Button></Td>
                  )}
                  <Td><Badge tone={l.approval === "approved" ? "green" : l.approval === "rejected" ? "red" : "slate"}>{l.approval}</Badge></Td>
                  <Td>
                    <span className="flex gap-1.5">
                      <Button small disabled={action.busy || l.approval === "approved"} onClick={() => decide(l, "approved")}>Approve</Button>
                      <Button small variant="danger" disabled={action.busy || l.approval === "rejected"} onClick={() => decide(l, "rejected")}>Reject</Button>
                      {!isClient && <Button small variant="ghost" disabled={action.busy} onClick={() => act(() => api.del(`/api/campaigns/${c.id}/creators/${l.id}`))}>Remove</Button>}
                    </span>
                  </Td>
                </tr>
              ))}
            </Table>
          </div>
        </Card>
      )}
      {editing && <CampaignForm initial={c} clients={clients.data ?? []} onClose={() => setEditing(false)} onSaved={reload} />}
    </>
  );
}
