import { useState } from "react";
import { Link } from "react-router-dom";
import { AddToCampaignModal, ExportButtons, Pager } from "../components/shared";
import { Avatar, Badge, Button, Empty, ErrorNote, Input, Notice, PageHeader, ScorePill, Select, SellingBadge, SkeletonRows, Table, Td, VerdictBadge } from "../components/ui";
import { useAction, useLoad } from "../hooks/useLoad";
import { api } from "../services/api";
import type { Creator, Meta, Paged } from "../types";
import { compact, day, label } from "../utils/format";

const SORTS = [
  { value: "lead_score", label: "Lead score" }, { value: "followers", label: "Followers" },
  { value: "median_reel_views", label: "Median reel views" }, { value: "created_at", label: "Date added" },
  { value: "last_collected_at", label: "Last collected" }, { value: "follow_up_date", label: "Follow-up date" },
  { value: "username", label: "Username" },
];

/** Creator Database. With review=true it becomes the Needs Review queue. */
export function Creators({ review = false }: { review?: boolean }) {
  const meta = useLoad(() => api.get<Meta>("/api/meta"));
  const [f, setF] = useState({
    search: "", niche: "", country: "", selling_status: "", crm_status: "", verdict: review ? "needs_review" : "",
    has_email: "", tag: "", sort: "lead_score", order: "desc",
  });
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [adding, setAdding] = useState(false);
  const [flash, setFlash] = useState("");
  const action = useAction();
  const list = useLoad(
    () => api.get<Paged<Creator>>("/api/creators", { ...f, page, page_size: 25 }),
    [JSON.stringify(f), page],
  );
  const set = (patch: Partial<typeof f>) => { setF((x) => ({ ...x, ...patch })); setPage(1); };
  const items = list.data?.items ?? [];
  const allSelected = items.length > 0 && items.every((c) => selected.has(c.id));

  const toggle = (id: number, on: boolean) => setSelected((prev) => {
    const next = new Set(prev);
    if (on) next.add(id); else next.delete(id);
    return next;
  });

  const setStatus = async (c: Creator, crm_status: string) => {
    const ok = await action.run(() => api.patch(`/api/creators/${c.id}`, { crm_status }));
    if (ok) { setFlash(`@${c.username} moved to ${crm_status}.`); void list.reload(); }
  };

  return (
    <>
      <PageHeader title={review ? "Needs Review" : "Creator Database"}
        subtitle={review ? "Creators the rules could not decide on. Check them and approve or reject." : "Every creator found so far, stored once."}
        action={<>
          <Button small variant="secondary" disabled={selected.size === 0} onClick={() => setAdding(true)}>Add to campaign ({selected.size})</Button>
          <ExportButtons params={{ scope: "selected", ids: [...selected].join(",") }} disabled={selected.size === 0} label="Export selected" />
        </>} />

      <div className="mb-4 grid gap-3 rounded-lg border border-slate-200 bg-white p-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6">
        <Input aria-label="Search" placeholder="Search name, username, bio" value={f.search} onChange={(e) => set({ search: e.target.value })} />
        <Select aria-label="Niche" value={f.niche} onChange={(e) => set({ niche: e.target.value })} placeholder="All niches" options={meta.data?.niches ?? []} />
        <Select aria-label="Country" value={f.country} onChange={(e) => set({ country: e.target.value })} placeholder="All countries" options={meta.data?.countries ?? []} />
        <Select aria-label="Selling status" value={f.selling_status} onChange={(e) => set({ selling_status: e.target.value })} placeholder="Any selling status"
          options={(meta.data?.selling_statuses ?? []).map((s) => ({ value: s, label: label(s) }))} />
        <Select aria-label="CRM status" value={f.crm_status} onChange={(e) => set({ crm_status: e.target.value })} placeholder="Any CRM status" options={meta.data?.crm_statuses ?? []} />
        {!review && (
          <Select aria-label="Verdict" value={f.verdict} onChange={(e) => set({ verdict: e.target.value })} placeholder="Any verdict"
            options={[{ value: "qualified", label: "Qualified" }, { value: "needs_review", label: "Needs review" }, { value: "rejected", label: "Rejected" }]} />
        )}
        <Select aria-label="Email" value={f.has_email} onChange={(e) => set({ has_email: e.target.value })} placeholder="Email: any"
          options={[{ value: "true", label: "Has public email" }, { value: "false", label: "No public email" }]} />
        <Input aria-label="Tag" placeholder="Tag" value={f.tag} onChange={(e) => set({ tag: e.target.value })} />
        <Select aria-label="Sort by" value={f.sort} onChange={(e) => set({ sort: e.target.value })} options={SORTS} />
        <Select aria-label="Order" value={f.order} onChange={(e) => set({ order: e.target.value })}
          options={[{ value: "desc", label: "High to low" }, { value: "asc", label: "Low to high" }]} />
      </div>

      <div className="space-y-3">
        <ErrorNote error={list.error || action.error} />
        {flash && <Notice tone="success">{flash}</Notice>}
        {list.loading && !list.data ? <SkeletonRows rows={8} /> : items.length === 0 ? (
          <Empty title={review ? "Nothing waiting for review" : "No creators match"}
            text={review ? "New searches will add creators here when the rules are unsure." : "Change the filters, or run a search on the Discover page."} />
        ) : (
          <Table head={[
            <input key="all" type="checkbox" aria-label="Select all on this page" checked={allSelected}
              onChange={(e) => setSelected((prev) => { const next = new Set(prev); items.forEach((c) => (e.target.checked ? next.add(c.id) : next.delete(c.id))); return next; })} />,
            "Creator", "Followers", "Reel views", "Score", "Verdict", "Selling", "Email", "CRM status", "Collected", "",
          ]}>
            {items.map((c) => (
              <tr key={c.id} className="hover:bg-slate-50">
                <Td><input type="checkbox" aria-label={`Select ${c.username}`} checked={selected.has(c.id)} onChange={(e) => toggle(c.id, e.target.checked)} /></Td>
                <Td>
                  <div className="flex items-center gap-2.5">
                    <Avatar name={c.full_name || c.username} url={c.profile_pic_url} size={32} />
                    <div className="min-w-0">
                      <Link to={`/creators/${c.id}`} className="font-medium text-slate-900 hover:text-indigo-700">@{c.username}</Link>
                      <div className="flex flex-wrap items-center gap-1 text-xs text-slate-500">
                        {c.niche && <span>{c.niche}</span>}{c.country && <span>· {c.country}</span>}
                      </div>
                    </div>
                  </div>
                </Td>
                <Td className="tabular-nums">{compact(c.followers)}</Td>
                <Td className="tabular-nums">{compact(c.median_reel_views)}</Td>
                <Td><ScorePill score={c.lead_score} confidence={c.confidence} /></Td>
                <Td><VerdictBadge verdict={c.verdict} /></Td>
                <Td><SellingBadge status={c.selling_status} /></Td>
                <Td>{c.has_email ? <Badge tone="green">Yes</Badge> : <Badge>No</Badge>}</Td>
                <Td>{c.crm_status}</Td>
                <Td className="whitespace-nowrap text-xs text-slate-500">{c.collected ? day(c.last_collected_at) : "Not collected"}</Td>
                <Td>
                  {review ? (
                    <span className="flex gap-1.5">
                      <Button small disabled={action.busy} onClick={() => setStatus(c, "Qualified")}>Approve</Button>
                      <Button small variant="danger" disabled={action.busy} onClick={() => setStatus(c, "Rejected")}>Reject</Button>
                    </span>
                  ) : <Link to={`/creators/${c.id}`} className="text-xs font-medium text-indigo-700 hover:underline">Open</Link>}
                </Td>
              </tr>
            ))}
          </Table>
        )}
        {list.data && <Pager page={page} pageSize={25} total={list.data.total} onPage={setPage} />}
      </div>
      {adding && <AddToCampaignModal creatorIds={[...selected]} onClose={() => setAdding(false)} onDone={setFlash} />}
    </>
  );
}
