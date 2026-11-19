import { Link } from "react-router-dom";
import type { Creator } from "../types";
import { compact, day } from "../utils/format";
import { Avatar, Badge, Button, ScorePill, SellingBadge, VerdictBadge } from "./ui";

interface Props {
  creator: Creator;
  selected?: boolean;
  onSelect?: (id: number, on: boolean) => void;
  onAddToCampaign?: (creator: Creator) => void;
  onApprove?: (creator: Creator) => void;
  onReject?: (creator: Creator) => void;
}

export function CreatorCard({ creator: c, selected, onSelect, onAddToCampaign, onApprove, onReject }: Props) {
  return (
    <article className="flex flex-col rounded-lg border border-slate-200 bg-white p-4" data-testid="creator-card">
      <div className="flex items-start gap-3">
        {onSelect && (
          <input type="checkbox" aria-label={`Select ${c.username}`} checked={!!selected}
            onChange={(e) => onSelect(c.id, e.target.checked)} className="mt-3 h-4 w-4 rounded border-slate-300 text-indigo-600" />
        )}
        <Avatar name={c.full_name || c.username} url={c.profile_pic_url} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <Link to={`/creators/${c.id}`} className="truncate text-sm font-semibold text-slate-900 hover:text-indigo-700">@{c.username}</Link>
          </div>
          <p className="truncate text-sm text-slate-500">{c.full_name || "Name not available"}</p>
        </div>
        <ScorePill score={c.lead_score} confidence={c.confidence} />
      </div>

      <dl className="mt-3 grid grid-cols-3 gap-2 text-center">
        {[
          ["Followers", compact(c.followers)],
          ["Median reel views", compact(c.median_reel_views)],
          ["Reels checked", c.collected ? String(c.reels_analyzed) : "—"],
        ].map(([k, v]) => (
          <div key={k} className="rounded-md bg-slate-50 px-1 py-1.5">
            <dd className="text-sm font-semibold tabular-nums text-slate-900">{v}</dd>
            <dt className="text-[11px] text-slate-500">{k}</dt>
          </div>
        ))}
      </dl>

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <VerdictBadge verdict={c.verdict} />
        <SellingBadge status={c.selling_status} />
        <Badge tone={c.has_email ? "green" : "slate"}>{c.has_email ? "Public email" : "No public email"}</Badge>
        {c.niche && <Badge>{c.niche}</Badge>}
        {c.country && <Badge>{c.country}</Badge>}
        {c.from_cache && <Badge tone="indigo" title="Reused from the cache, no new collection">Cached</Badge>}
      </div>

      <p className="mt-2 line-clamp-2 min-h-8 text-xs text-slate-500">{c.verdict_reasons.join(" ")}</p>
      <p className="mt-1 text-[11px] text-slate-400">
        {c.collected ? `Data collected ${day(c.last_collected_at)}` : "Profile data not collected"}
      </p>

      <div className="mt-3 flex flex-wrap gap-2 border-t border-slate-100 pt-3">
        <Link to={`/creators/${c.id}`} className="inline-flex items-center rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50">View profile</Link>
        {onAddToCampaign && <Button small variant="secondary" onClick={() => onAddToCampaign(c)}>Add to campaign</Button>}
        {onApprove && <Button small onClick={() => onApprove(c)}>Approve</Button>}
        {onReject && <Button small variant="danger" onClick={() => onReject(c)}>Reject</Button>}
      </div>
    </article>
  );
}
