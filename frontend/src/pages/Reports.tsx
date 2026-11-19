import { useState } from "react";
import { ExportButtons } from "../components/shared";
import { Card, Empty, ErrorNote, PageHeader, Select, SkeletonRows, Table, Td } from "../components/ui";
import { useLoad } from "../hooks/useLoad";
import { api } from "../services/api";
import type { Campaign, SearchRun } from "../types";
import { dateTime } from "../utils/format";

export function Reports() {
  const campaigns = useLoad(() => api.get<Campaign[]>("/api/campaigns"));
  const runs = useLoad(() => api.get<SearchRun[]>("/api/discovery/runs"));
  const [campaignId, setCampaignId] = useState("");

  return (
    <>
      <PageHeader title="Reports" subtitle="Download lead sheets as Excel or CSV." />
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Lead lists">
          <ul className="divide-y divide-slate-100">
            {([["qualified", "Qualified leads", "Creators that meet every filter."],
               ["needs_review", "Needs review", "Creators waiting for a manual check."],
               ["rejected", "Rejected", "Creators that failed a filter, with the reason."],
               ["all", "Complete database", "Every creator stored."]] as const).map(([scope, title, text]) => (
              <li key={scope} className="flex flex-wrap items-center justify-between gap-2 py-3">
                <div><p className="text-sm font-medium text-slate-800">{title}</p><p className="text-xs text-slate-500">{text}</p></div>
                <ExportButtons params={{ scope }} />
              </li>
            ))}
          </ul>
        </Card>
        <Card title="Client campaign report">
          <p className="mb-3 text-sm text-slate-500">All creators in one campaign, with its name on every row.</p>
          <div className="flex flex-wrap items-center gap-3">
            <Select aria-label="Campaign" className="max-w-xs" value={campaignId} onChange={(e) => setCampaignId(e.target.value)} placeholder="Choose a campaign"
              options={(campaigns.data ?? []).map((c) => ({ value: c.id, label: c.name }))} />
            <ExportButtons params={{ scope: "campaign", campaign_id: campaignId }} disabled={!campaignId} />
          </div>
        </Card>
      </div>
      <h2 className="mb-2 mt-6 text-sm font-semibold text-slate-800">Search history</h2>
      <ErrorNote error={runs.error} />
      {runs.loading && !runs.data ? <SkeletonRows /> : !runs.data?.length ? <Empty title="No searches yet" text="Each search you run is listed here with its full results." /> : (
        <Table head={["When", "Search", "Source", "Found", "Qualified", "Review", "Rejected", "Export results"]}>
          {runs.data.map((r) => (
            <tr key={r.id}>
              <Td className="whitespace-nowrap text-xs text-slate-500">{dateTime(r.created_at)}</Td>
              <Td>{String(r.params.niche || "—")}</Td>
              <Td className="text-xs">{r.discovery_source} / {r.profile_provider}</Td>
              <Td className="tabular-nums">{r.discovered}</Td>
              <Td className="tabular-nums">{r.qualified}</Td>
              <Td className="tabular-nums">{r.needs_review}</Td>
              <Td className="tabular-nums">{r.rejected}</Td>
              <Td><ExportButtons params={{ scope: "search", run_id: r.id }} label="" /></Td>
            </tr>
          ))}
        </Table>
      )}
    </>
  );
}
