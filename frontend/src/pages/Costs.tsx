import { useState } from "react";
import { Badge, Button, Card, Empty, ErrorNote, Notice, PageHeader, SkeletonRows, Stat, Table, Td } from "../components/ui";
import { useLoad } from "../hooks/useLoad";
import { api } from "../services/api";
import type { Budget, Settings } from "../types";
import { dateTime, inr, num, usd } from "../utils/format";

interface Usage {
  searches: number; demo_searches: number; profiles_requested: number; profiles_collected: number; profiles_cached: number;
  profiles_failed: number; actor_runs: number; estimated_cost_usd: number | null; actual_cost_usd: number | null;
  best_known_cost_usd: number; cost_per_profile_usd: number | null; cost_per_qualified_usd: number | null;
  estimated_cost_inr: number | null; actual_cost_inr: number | null; best_known_cost_inr: number | null;
  cost_per_profile_inr: number | null; cost_per_qualified_inr: number | null;
}
interface Report {
  month: Usage; all_time: Usage; budget: Budget; fx: Settings["fx"]; apify_pricing: Settings["apify_pricing"];
  apify_limits: { limit_usd: number; used_usd: number; remaining_usd: number } | null; provider_note: string | null;
  provider_mode: string; apify_token_configured: boolean; max_profiles_per_search: number;
  recent_runs: { id: number; created_at: string; source: string; provider: string; is_demo: boolean; requested: number; collected: number;
    cached: number; qualified: number; actor_runs: number; est_cost_usd: number | null; actual_cost_usd: number | null }[];
}

export function Costs() {
  const [check, setCheck] = useState(false);
  const { data: r, loading, error } = useLoad(() => api.get<Report>("/api/costs", { check_provider: check }), [check]);

  if (loading && !r) return <SkeletonRows rows={6} />;
  if (!r) return <ErrorNote error={error} />;
  const m = r.month;
  const both = (u: number | null, i: number | null) => (u === null ? "—" : `${inr(i)} (${usd(u)})`);

  return (
    <>
      <PageHeader title="Cost & Usage" subtitle="What searches have used this month. Estimates and provider-reported charges are shown separately." />
      <div className="mb-4 space-y-2">
        <ErrorNote error={error} />
        {r.provider_mode === "mock"
          ? <Notice tone="success">Demo mode is on. No external provider is called, so the running cost is ₹0.</Notice>
          : <Notice tone="warn">Live mode is on. Every external search still asks for confirmation first.</Notice>}
        {r.budget.level === "blocked" && <Notice tone="error">Cash spend is over the monthly budget. Paid collection is blocked.</Notice>}
        {r.budget.level === "warning" && <Notice tone="warn">Cash spend has reached {r.budget.percent_of_budget}% of the monthly budget.</Notice>}
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Monthly cash budget" value={inr(r.budget.monthly_budget_inr)} hint="Change in Settings" />
        <Stat label="Cash spent this month" value={inr(r.budget.cash_spend_inr_now)} hint="Provider cost beyond its free allowance"
          tone={r.budget.level === "blocked" ? "red" : r.budget.level === "warning" ? "amber" : "green"} />
        <Stat label="Provider charges (actual)" value={both(m.actual_cost_usd, m.actual_cost_inr)} hint="Reported by the provider" />
        <Stat label="Our estimates" value={both(m.estimated_cost_usd, m.estimated_cost_inr)} hint="Estimate only, not a charge" />
        <Stat label="Profiles requested" value={num(m.profiles_requested)} />
        <Stat label="Profiles collected" value={num(m.profiles_collected)} hint={`${num(m.profiles_failed)} failed`} />
        <Stat label="Served from cache" value={num(m.profiles_cached)} hint="No provider call needed" />
        <Stat label="Apify Actor runs" value={num(m.actor_runs)} hint="Runs are not the same as profiles" />
        <Stat label="Cost per collected profile" value={both(m.cost_per_profile_usd, m.cost_per_profile_inr)} hint="Live searches only" />
        <Stat label="Cost per qualified lead" value={both(m.cost_per_qualified_usd, m.cost_per_qualified_inr)} hint="Live searches only" />
        <Stat label="Searches this month" value={num(m.searches)} hint={`${num(m.demo_searches)} demo`} />
        <Stat label="Max profiles per search" value={num(r.max_profiles_per_search)} hint="Change in Settings" />
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Card title="Apify free allowance" action={<Button small variant="secondary" onClick={() => setCheck(true)} disabled={loading}>Check with Apify</Button>}>
          {!r.apify_token_configured ? <p className="text-sm text-slate-500">No Apify token is configured on the server, so Apify is not in use.</p>
            : r.apify_limits ? (
              <dl className="grid grid-cols-3 gap-3 text-sm">
                <div><dt className="text-xs text-slate-500">Monthly allowance</dt><dd className="font-semibold">{usd(r.apify_limits.limit_usd)}</dd></div>
                <div><dt className="text-xs text-slate-500">Used</dt><dd className="font-semibold">{usd(r.apify_limits.used_usd)}</dd></div>
                <div><dt className="text-xs text-slate-500">Remaining</dt><dd className="font-semibold">{usd(r.apify_limits.remaining_usd)}</dd></div>
              </dl>
            ) : <p className="text-sm text-slate-500">{r.provider_note ?? "Press “Check with Apify” to read your current allowance. This is a free call."}</p>}
        </Card>
        <Card title="Rates used for estimates">
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between gap-3"><dt className="text-slate-500">Exchange rate</dt>
              <dd className="text-right font-medium">$1 = ₹{r.fx.usd_inr}<br /><span className="text-xs font-normal text-slate-500">{r.fx.source}{r.fx.updated_at && `, ${dateTime(r.fx.updated_at)}`}</span></dd></div>
            <div className="flex justify-between gap-3"><dt className="text-slate-500">Apify price per profile</dt>
              <dd className="text-right font-medium">{r.apify_pricing.usd_per_profile === null ? "Not known yet" : usd(r.apify_pricing.usd_per_profile)}<br />
                <span className="text-xs font-normal text-slate-500">{r.apify_pricing.source ?? "Read from Apify at the first live search"}{r.apify_pricing.updated_at && `, ${dateTime(r.apify_pricing.updated_at)}`}</span></dd></div>
            <div className="flex justify-between gap-3"><dt className="text-slate-500">Apify price per reel</dt>
              <dd className="text-right font-medium">{r.apify_pricing.usd_per_reel == null ? "Not known yet" : usd(r.apify_pricing.usd_per_reel)}<br />
                <span className="text-xs font-normal text-slate-500">Reel views are a second, separate charge, bought only for creators that pass the first checks</span></dd></div>
          </dl>
        </Card>
      </div>

      <h2 className="mb-2 mt-6 text-sm font-semibold text-slate-800">Recent searches</h2>
      {r.recent_runs.length === 0 ? <Empty title="No searches yet" /> : (
        <Table head={["When", "Source / provider", "Requested", "Collected", "Cached", "Qualified", "Actor runs", "Estimate", "Actual"]}>
          {r.recent_runs.map((x) => (
            <tr key={x.id}>
              <Td className="whitespace-nowrap text-xs text-slate-500">{dateTime(x.created_at)}</Td>
              <Td className="text-xs">{x.source} / {x.provider} {x.is_demo && <Badge tone="violet">DEMO DATA</Badge>}</Td>
              <Td className="tabular-nums">{x.requested}</Td><Td className="tabular-nums">{x.collected}</Td><Td className="tabular-nums">{x.cached}</Td>
              <Td className="tabular-nums">{x.qualified}</Td><Td className="tabular-nums">{x.actor_runs}</Td>
              <Td className="tabular-nums">{usd(x.est_cost_usd)}</Td><Td className="tabular-nums">{usd(x.actual_cost_usd)}</Td>
            </tr>
          ))}
        </Table>
      )}
    </>
  );
}
