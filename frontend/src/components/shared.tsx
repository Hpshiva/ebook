import { useState } from "react";
import { useAction, useLoad } from "../hooks/useLoad";
import { api, downloadExport } from "../services/api";
import type { Campaign } from "../types";
import { Button, Checkbox, ErrorNote, Field, Modal, Notice, Select, Spinner } from "./ui";

/** Pick a campaign and add the given creators to it. */
export function AddToCampaignModal({ creatorIds, onClose, onDone }: { creatorIds: number[]; onClose: () => void; onDone?: (msg: string) => void }) {
  const campaigns = useLoad(() => api.get<Campaign[]>("/api/campaigns"));
  const [campaignId, setCampaignId] = useState("");
  const [shortlisted, setShortlisted] = useState(false);
  const action = useAction();

  const submit = async () => {
    const res = await action.run(() =>
      api.post<{ added: number; already_in_campaign: number }>(`/api/campaigns/${campaignId}/creators`, {
        creator_ids: creatorIds, shortlisted,
      }));
    if (res) {
      onDone?.(`${res.added} added${res.already_in_campaign ? `, ${res.already_in_campaign} already in the campaign` : ""}.`);
      onClose();
    }
  };

  return (
    <Modal title={`Add ${creatorIds.length} creator${creatorIds.length === 1 ? "" : "s"} to a campaign`} onClose={onClose}>
      {campaigns.loading ? <Spinner /> : !campaigns.data?.length ? (
        <Notice tone="warn">There are no campaigns yet. Create one on the Campaigns page first.</Notice>
      ) : (
        <div className="space-y-4">
          <Field label="Campaign">
            <Select aria-label="Campaign" value={campaignId} onChange={(e) => setCampaignId(e.target.value)} placeholder="Choose a campaign"
              options={campaigns.data.map((c) => ({ value: c.id, label: `${c.name}${c.client_name ? ` (${c.client_name})` : " (our own)"}` }))} />
          </Field>
          <Checkbox label="Shortlist now (visible to the client)" checked={shortlisted} onChange={setShortlisted} />
          <ErrorNote error={action.error || campaigns.error} />
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button disabled={!campaignId || action.busy} onClick={submit}>{action.busy ? "Adding…" : "Add to campaign"}</Button>
          </div>
        </div>
      )}
    </Modal>
  );
}

/** CSV + Excel download buttons for one export scope. */
export function ExportButtons({ params, disabled, label = "Export" }: { params: Record<string, string | number | boolean | undefined>; disabled?: boolean; label?: string }) {
  const action = useAction();
  const go = (fmt: "csv" | "xlsx") => action.run(() => downloadExport({ ...params, fmt }));
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <Button small variant="secondary" disabled={disabled || action.busy} onClick={() => go("xlsx")}>{label} Excel</Button>
      <Button small variant="secondary" disabled={disabled || action.busy} onClick={() => go("csv")}>{label} CSV</Button>
      {action.error && <span className="text-xs text-red-700">{action.error}</span>}
    </span>
  );
}

export function Pager({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="mt-3 flex items-center justify-between text-sm text-slate-500">
      <span>{total === 0 ? "No results" : `${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)} of ${total}`}</span>
      <span className="flex gap-2">
        <Button small variant="secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</Button>
        <Button small variant="secondary" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</Button>
      </span>
    </div>
  );
}
