import { useEffect, useState, type FormEvent } from "react";
import { CreatorCard } from "../components/CreatorCard";
import { AddToCampaignModal, ExportButtons } from "../components/shared";
import { Button, Card, Checkbox, Empty, ErrorNote, Field, Input, Modal, Notice, PageHeader, Select, Spinner, Stat, Textarea } from "../components/ui";
import { useAction, useLoad } from "../hooks/useLoad";
import { api } from "../services/api";
import type { Campaign, Confirmation, Creator, Meta, SearchRun, Settings, Verdict } from "../types";
import { inr, usd } from "../utils/format";

type RunResponse = Confirmation | { needs_confirmation: false; run: SearchRun };

const COUNTRIES = ["India", "United States", "United Kingdom", "Canada", "Australia"];

export function Discover() {
  const settings = useLoad(() => api.get<Settings>("/api/settings"));
  const meta = useLoad(() => api.get<Meta>("/api/meta"));
  const campaigns = useLoad(() => api.get<Campaign[]>("/api/campaigns"));
  const [form, setForm] = useState({
    discovery_source: "demo", profile_provider: "demo", niche: "fitness", sub_niche: "", country: "", language: "",
    category: "", usernames: "", hashtags: "", campaign_id: "", max_profiles: "", refresh: false,
  });
  const [filters, setFilters] = useState<Settings["filters"] | null>(null);
  const [confirm, setConfirm] = useState<Confirmation | null>(null);
  const [run, setRun] = useState<SearchRun | null>(null);
  const [tab, setTab] = useState<Verdict | "all">("all");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [adding, setAdding] = useState<number[] | null>(null);
  const [flash, setFlash] = useState("");
  const action = useAction();

  useEffect(() => {
    if (settings.data && !filters) setFilters(settings.data.filters);
  }, [settings.data, filters]);

  const live = settings.data?.provider_mode === "live";
  const set = (patch: Partial<typeof form>) => setForm((f) => ({ ...f, ...patch }));
  const setFilter = (patch: Partial<Settings["filters"]>) => setFilters((f) => (f ? { ...f, ...patch } : f));

  const changeSource = (source: string) => {
    // Keep the pairing sensible: demo data only exists in the demo provider.
    const provider = source === "demo" ? "demo" : source === "hashtag" ? "apify" : form.profile_provider === "demo" ? "none" : form.profile_provider;
    set({ discovery_source: source, profile_provider: provider });
  };

  const submit = async (confirmed: boolean) => {
    setFlash("");
    const body = {
      ...form, campaign_id: form.campaign_id ? Number(form.campaign_id) : null,
      max_profiles: form.max_profiles ? Number(form.max_profiles) : null, filters, confirmed,
    };
    const res = await action.run(() => api.post<RunResponse>("/api/discovery/run", body));
    if (!res) return;
    if (res.needs_confirmation) {
      setConfirm(res);
    } else {
      setConfirm(null);
      setRun(res.run);
      setSelected(new Set());
      setTab("all");
    }
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    void submit(false);
  };

  const decide = async (creator: Creator, status: "Qualified" | "Rejected") => {
    const updated = await action.run(() => api.patch<Creator>(`/api/creators/${creator.id}`, { crm_status: status }));
    if (updated && run) {
      setRun({ ...run, results: run.results?.map((r) => (r.id === creator.id ? { ...r, crm_status: updated.crm_status } : r)) });
      setFlash(`@${creator.username} marked ${status}.`);
    }
  };

  const results = run?.results ?? [];
  const shown = tab === "all" ? results : results.filter((r) => r.verdict === tab);
  const toggle = (id: number, on: boolean) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(id); else next.delete(id);
      return next;
    });

  if (settings.loading || !filters) return <Spinner />;

  return (
    <>
      <PageHeader title="Discover Creators" subtitle="Find creators, collect public profile data and qualify them against your filters." />
      {!live && (
        <div className="mb-4"><Notice>Demo mode: results are fictional DEMO DATA and free. Manual import also works. Live search needs to be enabled in Settings.</Notice></div>
      )}
      <form onSubmit={onSubmit} className="space-y-4">
        <Card title="What to search">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Discovery source">
              <Select aria-label="Discovery source" value={form.discovery_source} onChange={(e) => changeSource(e.target.value)}
                options={[
                  { value: "demo", label: "Demo data (free, fictional)" },
                  { value: "manual", label: "Manual import (usernames / URLs)" },
                  { value: "hashtag", label: `Instagram hashtag search via Apify${live ? "" : " (live mode off)"}` },
                  { value: "duckduckgo", label: `DuckDuckGo search, often blocked${live ? "" : " (live mode off)"}` },
                ]} />
            </Field>
            <Field label="Profile data provider">
              <Select aria-label="Profile data provider" value={form.profile_provider} onChange={(e) => set({ profile_provider: e.target.value })}
                options={form.discovery_source === "demo"
                  ? [{ value: "demo", label: "Demo data" }]
                  : [{ value: "none", label: "None (save usernames only)" },
                     { value: "apify", label: `Apify${live ? "" : " (live mode off)"}` },
                     { value: "demo", label: "Demo data (demo_ usernames only)" }]} />
            </Field>
            <Field label="Niche">
              <Input aria-label="Niche" list="niche-list" value={form.niche} onChange={(e) => set({ niche: e.target.value })} placeholder="e.g. fitness" />
              <datalist id="niche-list">{(meta.data?.niches ?? []).map((n) => <option key={n} value={n} />)}</datalist>
            </Field>
            <Field label="Sub-niche"><Input value={form.sub_niche} onChange={(e) => set({ sub_niche: e.target.value })} placeholder="optional" /></Field>
            <Field label="Country">
              <Select value={form.country} onChange={(e) => set({ country: e.target.value })} placeholder="Any country" options={COUNTRIES} />
            </Field>
            <Field label="Language"><Input value={form.language} onChange={(e) => set({ language: e.target.value })} placeholder="Any language" /></Field>
            <Field label="Campaign (optional)">
              <Select value={form.campaign_id} onChange={(e) => set({ campaign_id: e.target.value })} placeholder="No campaign"
                options={(campaigns.data ?? []).map((c) => ({ value: c.id, label: c.name }))} />
            </Field>
            <Field label="Max profiles" hint={`Limit per search: ${settings.data?.max_profiles_per_search}`}>
              <Input type="number" min={1} max={settings.data?.max_profiles_per_search} value={form.max_profiles}
                onChange={(e) => set({ max_profiles: e.target.value })} placeholder={String(settings.data?.max_profiles_per_search)} />
            </Field>
          </div>
          {form.discovery_source === "hashtag" && (
            <div className="mt-4">
              <Field label="Hashtags (optional)" hint="Up to 5, separated by spaces or commas. Leave empty to use the niche and sub-niche as hashtags. Each result is charged by Apify.">
                <Input aria-label="Hashtags" value={form.hashtags} onChange={(e) => set({ hashtags: e.target.value })} placeholder="homeworkout, fitnesscoach" />
              </Field>
            </div>
          )}
          {form.discovery_source === "manual" && (
            <div className="mt-4">
              <Field label="Instagram usernames or profile URLs" hint="One per line, or separated by commas or spaces.">
                <Textarea aria-label="Usernames" rows={4} value={form.usernames} onChange={(e) => set({ usernames: e.target.value })}
                  placeholder={"@username\nhttps://www.instagram.com/another/"} />
              </Field>
            </div>
          )}
        </Card>

        <Card title="Filters">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {([
              ["min_followers", "Min followers"], ["max_followers", "Max followers"],
              ["min_views", "Min median reel views"], ["max_views", "Max median reel views"], ["min_reels", "Min reels with views"],
            ] as const).map(([key, text]) => (
              <Field key={key} label={text}>
                <Input type="number" min={0} aria-label={text} value={filters[key]} onChange={(e) => setFilter({ [key]: Number(e.target.value) })} />
              </Field>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2">
            <Checkbox label="Require a public email" checked={filters.require_email} onChange={(v) => setFilter({ require_email: v })} />
            <Checkbox label="No email: send to Needs review (contact by DM)" disabled={!filters.require_email}
              checked={filters.require_email && filters.no_email_to_review} onChange={(v) => setFilter({ no_email_to_review: v })} />
            <Checkbox label="Exclude creators already selling" checked={filters.exclude_selling} onChange={(v) => setFilter({ exclude_selling: v })} />
            <Checkbox label="Public profiles only" checked={filters.require_public} onChange={(v) => setFilter({ require_public: v })} />
            <Checkbox label="Refresh cached profiles" checked={form.refresh} onChange={(v) => set({ refresh: v })} />
          </div>
        </Card>

        <ErrorNote error={action.error} />
        <Button type="submit" disabled={action.busy}>{action.busy ? "Searching…" : "Run search"}</Button>
      </form>

      {confirm && (
        <Modal title="Confirm external calls" onClose={() => setConfirm(null)}>
          <div className="space-y-3 text-sm text-slate-700">
            <p>This search will contact: <strong>{confirm.external_calls.join(" and ")}</strong>.</p>
            <p>Up to <strong>{confirm.max_profiles}</strong> profile(s) may be collected.</p>
            {confirm.estimate && (
              <Notice tone={confirm.estimate.large_search ? "warn" : "info"}>
                {confirm.estimate.estimated_usd === null
                  ? "The provider's current price could not be read, so no cost estimate is available."
                  : <>Estimated provider usage: <strong>up to {usd(confirm.estimate.estimated_usd)}</strong> ({inr(confirm.estimate.estimated_inr)}).
                      {confirm.estimate.discovery_usd ? <>{" "}Hashtag search: {usd(confirm.estimate.discovery_usd)}.</> : null}
                      {" "}Profiles: {usd(confirm.estimate.profiles_usd)}. Reel views: at most {usd(confirm.estimate.reels_usd_max)}, and only for creators
                      that pass the follower, email and selling checks. This is an estimate, not a charge.</>}
                {confirm.limits && <> Free allowance left this month: <strong>{usd(confirm.limits.remaining_usd)}</strong>.</>}
                {confirm.estimate.large_search && " This is a large search."}
              </Notice>
            )}
            {confirm.reasons.map((r) => <Notice key={r} tone="error">{r}</Notice>)}
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="secondary" onClick={() => setConfirm(null)}>Cancel</Button>
              <Button disabled={action.busy} onClick={() => submit(true)}>
                {action.busy ? "Running…" : confirm.allowed ? "Confirm and run" : "Run without collection"}
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {run && (
        <section className="mt-6 space-y-4" aria-label="Search results">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
            <Stat label="Discovered" value={run.discovered} />
            <Stat label="Collected" value={run.collected} />
            <Stat label="From cache" value={run.cached} />
            <Stat label="Failed" value={run.failed} />
            <Stat label="Qualified" value={run.qualified} tone="green" />
            <Stat label="Needs review" value={run.needs_review} tone="amber" />
            <Stat label="Rejected" value={run.rejected} tone="red" />
          </div>
          {run.messages.map((m) => <Notice key={m} tone={m.startsWith("DEMO DATA") ? "info" : "warn"}>{m}</Notice>)}
          {flash && <Notice tone="success">{flash}</Notice>}

          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap gap-1" role="tablist">
              {([["all", `All (${results.length})`], ["qualified", `Qualified (${run.qualified})`],
                 ["needs_review", `Needs review (${run.needs_review})`], ["rejected", `Rejected (${run.rejected})`]] as const).map(([key, text]) => (
                <button key={key} type="button" role="tab" aria-selected={tab === key} onClick={() => setTab(key)}
                  className={`rounded-md px-3 py-1.5 text-sm ${tab === key ? "bg-slate-900 text-white" : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"}`}>
                  {text}
                </button>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button small variant="secondary" disabled={selected.size === 0} onClick={() => setAdding([...selected])}>
                Add selected to campaign ({selected.size})
              </Button>
              <ExportButtons params={{ scope: "search", run_id: run.id }} disabled={results.length === 0} />
            </div>
          </div>

          {shown.length === 0 ? <Empty title="No creators in this view" text="Try another tab or loosen the filters." /> : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {shown.map((c) => (
                <CreatorCard key={c.id} creator={c} selected={selected.has(c.id)} onSelect={toggle}
                  onAddToCampaign={(x) => setAdding([x.id])} onApprove={(x) => decide(x, "Qualified")} onReject={(x) => decide(x, "Rejected")} />
              ))}
            </div>
          )}
        </section>
      )}
      {adding && <AddToCampaignModal creatorIds={adding} onClose={() => setAdding(null)} onDone={setFlash} />}
    </>
  );
}
