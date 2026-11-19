import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AddToCampaignModal } from "../components/shared";
import { Avatar, Badge, Button, Card, ErrorNote, Field, Input, Notice, PageHeader, ScorePill, Select, SellingBadge, Spinner, Textarea, VerdictBadge } from "../components/ui";
import { useAction, useLoad } from "../hooks/useLoad";
import { api } from "../services/api";
import type { Creator, CreatorDetail as Detail, Meta, OutreachMessage } from "../types";
import { compact, dateTime, label, num } from "../utils/format";

export function CreatorDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const meta = useLoad(() => api.get<Meta>("/api/meta"));
  const { data: c, loading, error, setData } = useLoad(() => api.get<Detail>(`/api/creators/${id}`), [id]);
  const similar = useLoad(() => api.get<{ similar: Creator[]; not_yet_collected: string[] }>(`/api/creators/${id}/similar`), [id]);
  const action = useAction();
  const [note, setNote] = useState("");
  const [tag, setTag] = useState("");
  const [override, setOverride] = useState({ status: "", note: "" });
  const [adding, setAdding] = useState(false);
  const [flash, setFlash] = useState("");
  const [draft, setDraft] = useState<OutreachMessage | null>(null);

  if (loading && !c) return <Spinner />;
  if (!c) return <ErrorNote error={error || "Creator not found"} />;

  const apply = async (fn: () => Promise<Detail>, message = "") => {
    const updated = await action.run(fn);
    if (updated) { setData(updated); setFlash(message); }
  };
  const patch = (body: Record<string, unknown>, message = "Saved.") => apply(() => api.patch<Detail>(`/api/creators/${c.id}`, body), message);

  const remove = async () => {
    if (!window.confirm(`Delete @${c.username} and all stored data about them? This cannot be undone.`)) return;
    if (await action.run(() => api.del(`/api/creators/${c.id}`))) navigate("/creators");
  };
  const makeDraft = async () => {
    const d = await action.run(() => api.post<OutreachMessage>("/api/outreach/draft", { creator_id: c.id }));
    if (d) setDraft(d);
  };

  return (
    <>
      <PageHeader title={`@${c.username}`}
        subtitle={<span className="flex flex-wrap items-center gap-2">{c.full_name || "Name not available"}
          <a href={c.profile_url} target="_blank" rel="noreferrer noopener" className="text-indigo-700 hover:underline">Open on Instagram ↗</a></span>}
        action={<>
          <Button small variant="secondary" onClick={() => setAdding(true)}>Add to campaign</Button>
          <Button small variant="secondary" disabled={action.busy} onClick={makeDraft}>Create outreach draft</Button>
          <Button small variant="danger" disabled={action.busy} onClick={remove}>Delete</Button>
        </>} />
      <div className="mb-4 space-y-2">
        <ErrorNote error={action.error} />
        {flash && <Notice tone="success">{flash}</Notice>}
        {!c.collected && <Notice tone="warn">Profile data has not been collected for this creator, so most fields are empty. Nothing has been estimated or invented.</Notice>}
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <Card title="Profile">
            <div className="flex items-start gap-4">
              <Avatar name={c.full_name || c.username} url={c.profile_pic_url} size={56} />
              <div className="min-w-0 flex-1">
                <p className="whitespace-pre-line text-sm text-slate-700">{c.biography || "No biography available."}</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <VerdictBadge verdict={c.verdict} />
                  {c.business_category && <Badge>{c.business_category}</Badge>}
                  {c.niche && <Badge>{c.niche}</Badge>}{c.country && <Badge>{c.country}</Badge>}{c.language && <Badge>{c.language}</Badge>}
                  {c.is_private && <Badge tone="red">Private</Badge>}{c.is_verified && <Badge tone="indigo">Verified</Badge>}
                </div>
                {c.external_urls.length > 0 && (
                  <ul className="mt-2 space-y-0.5 text-sm">
                    {c.external_urls.map((u) => <li key={u}><a href={u} target="_blank" rel="noreferrer noopener nofollow" className="break-all text-indigo-700 hover:underline">{u}</a></li>)}
                  </ul>
                )}
              </div>
            </div>
            <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-5">
              {[["Followers", num(c.followers)], ["Following", num(c.following)], ["Posts", num(c.posts_count)],
                ["Median reel views", num(c.median_reel_views)], ["Engagement", c.engagement_rate === null ? "—" : `${c.engagement_rate}%`]].map(([k, v]) => (
                <div key={k} className="rounded-md bg-slate-50 p-2.5"><dt className="text-xs text-slate-500">{k}</dt><dd className="text-sm font-semibold tabular-nums text-slate-900">{v}</dd></div>
              ))}
            </dl>
            <p className="mt-3 text-xs text-slate-500">
              {c.reels_analyzed} reel(s) with view counts in the sample the provider returned
              {c.reel_views.length > 0 && <>: {c.reel_views.map(compact).join(", ")}</>}. This is a sample, not every recent reel.
              {" "}Last collected: {dateTime(c.last_collected_at)}{c.data_provider && ` via ${c.data_provider}`}.
            </p>
            <ul className="mt-3 list-disc space-y-0.5 pl-5 text-sm text-slate-600">{c.verdict_reasons.map((r) => <li key={r}>{r}</li>)}</ul>
          </Card>

          <Card title="Lead score" action={<ScorePill score={c.lead_score} confidence={c.confidence} />}>
            <p className="mb-3 text-xs text-slate-500">
              Confidence: <strong>{c.confidence}</strong>. Criteria without data are left out, not counted as zero. A score is a guide and does not guarantee sales.
            </p>
            <ul className="space-y-2">
              {Object.entries(c.score_breakdown).map(([key, part]) => (
                <li key={key} className="text-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-slate-700">{label(key)}</span>
                    <span className="tabular-nums text-slate-600">{part.points === null ? "no data" : `${part.points} / ${part.weight}`}</span>
                  </div>
                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
                    <div className={`h-full rounded-full ${part.points === null ? "bg-slate-300" : "bg-indigo-500"}`}
                      style={{ width: `${part.points === null || !part.weight ? 0 : (part.points / part.weight) * 100}%` }} />
                  </div>
                  <p className="mt-0.5 text-xs text-slate-500">{part.note}</p>
                </li>
              ))}
            </ul>
          </Card>

          <Card title="Selling status" action={<SellingBadge status={c.selling_status} />}>
            <p className="text-xs text-slate-500">Rule-based check of the biography, links and captions. It cannot guarantee a creator is not selling products.</p>
            <ul className="mt-2 list-disc space-y-0.5 pl-5 text-sm text-slate-700">{c.selling_reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            {c.selling_override && (
              <div className="mt-3"><Notice tone="warn">
                Manually set to <strong>{label(c.selling_override.status)}</strong> by {c.selling_override.by} on {dateTime(c.selling_override.at)}
                {c.selling_override.note && `: ${c.selling_override.note}`}. Rules detected: {label(c.selling_detected)}.
              </Notice></div>
            )}
            <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_2fr_auto_auto]">
              <Select aria-label="Override status" value={override.status} onChange={(e) => setOverride({ ...override, status: e.target.value })} placeholder="Override to…"
                options={(meta.data?.selling_statuses ?? []).map((s) => ({ value: s, label: label(s) }))} />
              <Input aria-label="Override note" placeholder="Why? (recorded with your name)" value={override.note} onChange={(e) => setOverride({ ...override, note: e.target.value })} />
              <Button small disabled={!override.status || action.busy}
                onClick={() => apply(() => api.post<Detail>(`/api/creators/${c.id}/selling-override`, override), "Override saved.")}>Save override</Button>
              {c.selling_override && <Button small variant="secondary" disabled={action.busy}
                onClick={() => apply(() => api.post<Detail>(`/api/creators/${c.id}/selling-override`, { status: null }), "Override removed.")}>Clear</Button>}
            </div>
          </Card>

          <Card title="Public contacts">
            {c.contacts.length === 0 ? <p className="text-sm text-slate-500">No public contact was found on the profile. Contacts are never guessed.</p> : (
              <ul className="divide-y divide-slate-100">
                {c.contacts.map((x) => (
                  <li key={x.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                    <div>
                      <p className="font-medium text-slate-900">{x.value}</p>
                      <p className="text-xs text-slate-500">{label(x.type)} · from {x.source} · found {dateTime(x.discovered_at)}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge tone={x.validation_status === "mx_checked" ? "green" : x.validation_status.includes("no_mail") ? "red" : "slate"}>{label(x.validation_status)}</Badge>
                      {x.type === "email" && <Button small variant="secondary" disabled={action.busy}
                        onClick={() => apply(() => api.post<Detail>(`/api/creators/${c.id}/contacts/${x.id}/verify`), "Domain checked.")}>Check domain</Button>}
                      <Button small variant="danger" disabled={action.busy}
                        onClick={() => apply(() => api.del<Detail>(`/api/creators/${c.id}/contacts/${x.id}`), "Contact deleted.")}>Delete</Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Similar creators">
            {similar.loading ? <Spinner /> : !similar.data?.similar.length ? <p className="text-sm text-slate-500">No similar creators in the database yet.</p> : (
              <ul className="divide-y divide-slate-100">
                {similar.data.similar.map((s) => (
                  <li key={s.id} className="py-2 text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <Link to={`/creators/${s.id}`} className="font-medium text-slate-900 hover:text-indigo-700">@{s.username}</Link>
                      <span className="text-xs text-slate-500">{compact(s.followers)} followers · similarity {s.similarity}</span>
                    </div>
                    <p className="text-xs text-slate-500">{s.similar_reasons?.join(" · ")}</p>
                  </li>
                ))}
              </ul>
            )}
            {!!similar.data?.not_yet_collected.length && (
              <p className="mt-2 text-xs text-slate-500">Related accounts reported by the provider but not collected yet: {similar.data.not_yet_collected.map((u) => `@${u}`).join(", ")}</p>
            )}
          </Card>
        </div>

        <div className="space-y-5">
          <Card title="Pipeline">
            <div className="space-y-3">
              <Field label="CRM status">
                <Select aria-label="CRM status" value={c.crm_status} onChange={(e) => patch({ crm_status: e.target.value }, "Status updated.")} options={meta.data?.crm_statuses ?? [c.crm_status]} />
              </Field>
              <Field label="Owner">
                <Select aria-label="Owner" value={c.owner_id ?? ""} placeholder="Unassigned"
                  onChange={(e) => patch({ owner_id: e.target.value ? Number(e.target.value) : null }, "Owner updated.")}
                  options={(meta.data?.owners ?? []).map((o) => ({ value: o.id, label: o.name }))} />
              </Field>
              <Field label="Follow-up date">
                <Input type="date" aria-label="Follow-up date" value={c.follow_up_date ?? ""} onChange={(e) => patch({ follow_up_date: e.target.value || null }, "Follow-up saved.")} />
              </Field>
              <div>
                <p className="mb-1 text-sm font-medium text-slate-700">Tags</p>
                <div className="mb-2 flex flex-wrap gap-1.5">
                  {c.tags.length === 0 && <span className="text-xs text-slate-500">No tags</span>}
                  {c.tags.map((t) => (
                    <button key={t} type="button" title="Remove tag" onClick={() => patch({ tags: c.tags.filter((x) => x !== t) })}
                      className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700 hover:bg-red-50 hover:text-red-700">{t} ✕</button>
                  ))}
                </div>
                <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (tag.trim()) { void patch({ tags: [...c.tags, tag.trim()] }); setTag(""); } }}>
                  <Input aria-label="New tag" placeholder="Add a tag" value={tag} onChange={(e) => setTag(e.target.value)} />
                  <Button small type="submit" variant="secondary">Add</Button>
                </form>
              </div>
              {c.campaigns.length > 0 && (
                <div>
                  <p className="mb-1 text-sm font-medium text-slate-700">Campaigns</p>
                  <ul className="space-y-1 text-sm">{c.campaigns.map((x) => (
                    <li key={x.campaign_id}><Link className="text-indigo-700 hover:underline" to={`/campaigns/${x.campaign_id}`}>{x.name}</Link> <span className="text-xs text-slate-500">({x.approval})</span></li>
                  ))}</ul>
                </div>
              )}
            </div>
          </Card>

          <Card title="Notes & activity">
            <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); if (note.trim()) { void apply(() => api.post<Detail>(`/api/creators/${c.id}/notes`, { text: note }), "Note added."); setNote(""); } }}>
              <Textarea aria-label="Note" rows={2} placeholder="Add a note" value={note} onChange={(e) => setNote(e.target.value)} />
              <Button small type="submit" disabled={!note.trim() || action.busy}>Add note</Button>
            </form>
            <ul className="mt-4 space-y-3">
              {c.activities.map((a) => (
                <li key={a.id} className="text-sm">
                  <p className="text-slate-800"><span className="font-medium">{label(a.action)}</span>: {a.detail}</p>
                  <p className="text-xs text-slate-500">{a.user_name || "System"} · {dateTime(a.created_at)}</p>
                </li>
              ))}
            </ul>
          </Card>

          {c.history.length > 1 && (
            <Card title="Collection history">
              <ul className="space-y-1 text-xs text-slate-600">
                {c.history.map((h) => <li key={h.collected_at}>{dateTime(h.collected_at)}: {num(h.followers)} followers, {num(h.median_reel_views)} median views</li>)}
              </ul>
            </Card>
          )}
        </div>
      </div>
      {adding && <AddToCampaignModal creatorIds={[c.id]} onClose={() => setAdding(false)} onDone={setFlash} />}
      {draft && (
        <div className="fixed bottom-4 right-4 z-30 max-w-sm"><Notice tone="success">
          Outreach draft created. <Link to="/outreach" className="font-medium underline">Review it in Outreach</Link>.
          <button type="button" className="ml-2 underline" onClick={() => setDraft(null)}>Dismiss</button>
        </Notice></div>
      )}
    </>
  );
}
