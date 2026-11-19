import { useState } from "react";
import { Link } from "react-router-dom";
import { Card, Empty, ErrorNote, Field, Input, Notice, PageHeader, Select, SkeletonRows, Stat } from "../components/ui";
import { useLoad } from "../hooks/useLoad";
import { api } from "../services/api";
import type { Campaign, Dashboard } from "../types";
import { inr, num } from "../utils/format";

export function Overview() {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [campaignId, setCampaignId] = useState("");
  const campaigns = useLoad(() => api.get<Campaign[]>("/api/campaigns"));
  const { data: d, loading, error } = useLoad(
    () => api.get<Dashboard>("/api/dashboard", { date_from: from, date_to: to, campaign_id: campaignId }),
    [from, to, campaignId],
  );
  const maxStatus = d ? Math.max(1, ...Object.values(d.crm_statuses)) : 1;

  return (
    <>
      <PageHeader title="Overview" subtitle="Live counts from your database." />
      <div className="mb-5 grid gap-3 rounded-lg border border-slate-200 bg-white p-4 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="From"><Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
        <Field label="To"><Input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
        <Field label="Campaign">
          <Select value={campaignId} onChange={(e) => setCampaignId(e.target.value)} placeholder="All campaigns"
            options={(campaigns.data ?? []).map((c) => ({ value: c.id, label: c.name }))} />
        </Field>
      </div>
      <ErrorNote error={error} />
      {loading && !d ? <SkeletonRows rows={6} /> : d && (
        <div className="space-y-5">
          {!d.apify_token_configured && (
            <Notice tone="warn">No Apify token is saved, so searches cannot collect real data yet. Add it in Settings → Apify token.</Notice>
          )}
          {d.creators_total === 0 && (
            <Empty title="No creators yet" text="Run your first search to fill the dashboard."
              action={<Link to="/discover" className="rounded-md bg-indigo-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-indigo-700">Discover creators</Link>} />
          )}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <Stat label="Creators discovered" value={num(d.creators_total)} />
            <Stat label="Qualified" value={num(d.qualified)} tone="green" />
            <Stat label="Needs review" value={num(d.needs_review)} tone="amber" />
            <Stat label="Rejected" value={num(d.rejected)} tone="red" />
            <Stat label="With public email" value={num(d.with_email)} />
            <Stat label="Searches" value={num(d.searches)} />
            <Stat label="Active campaigns" value={num(d.active_campaigns)} />
            <Stat label="Clients" value={num(d.clients)} />
            <Stat label="Follow-ups due" value={num(d.follow_ups_due)} tone={d.follow_ups_due ? "amber" : undefined} />
            <Stat label="Provider cost" value={inr(d.cost.best_known_inr)}
              hint={d.cost.live_searches === 0 ? "No live searches yet" : d.cost.has_actuals ? "Includes provider-reported charges" : "Estimate only"} />
          </div>
          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Pipeline by CRM status">
              {Object.keys(d.crm_statuses).length === 0 ? <p className="text-sm text-slate-500">Nothing in the pipeline yet.</p> : (
                <ul className="space-y-2">
                  {Object.entries(d.crm_statuses).sort((a, b) => b[1] - a[1]).map(([status, count]) => (
                    <li key={status} className="flex items-center gap-3 text-sm">
                      <span className="w-28 shrink-0 text-slate-600">{status}</span>
                      <span className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
                        <span className="block h-full rounded-full bg-indigo-500" style={{ width: `${(count / maxStatus) * 100}%` }} />
                      </span>
                      <span className="w-8 text-right font-medium tabular-nums text-slate-800">{count}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card title="Outreach status">
              <div className="grid grid-cols-2 gap-3">
                {[["Drafts", d.outreach.draft], ["Contacted", d.outreach.contacted], ["Replied", d.outreach.replied], ["No reply", d.outreach.no_reply]].map(([k, v]) => (
                  <div key={k} className="rounded-md bg-slate-50 p-3">
                    <p className="text-xl font-semibold tabular-nums text-slate-900">{v}</p>
                    <p className="text-xs text-slate-500">{k}</p>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
