import { useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Button, Card, Empty, ErrorNote, Field, Input, Modal, Notice, PageHeader, Select, SkeletonRows, Textarea } from "../components/ui";
import { useAction, useLoad } from "../hooks/useLoad";
import { api } from "../services/api";
import type { OutreachMessage, Template } from "../types";
import { dateTime, label } from "../utils/format";

const TONE = { draft: "slate", contacted: "indigo", replied: "green", no_reply: "amber" } as const;

export function Outreach() {
  const [status, setStatus] = useState("");
  const list = useLoad(() => api.get<OutreachMessage[]>("/api/outreach", { status }), [status]);
  const templates = useLoad(() => api.get<{ placeholders: string[]; templates: Template[] }>("/api/outreach/templates"));
  const [open, setOpen] = useState<OutreachMessage | null>(null);
  const [template, setTemplate] = useState<Template | "new" | null>(null);
  const [tForm, setTForm] = useState({ name: "", subject: "", body: "" });
  const [copied, setCopied] = useState("");
  const action = useAction();

  const save = async (id: number, body: Record<string, unknown>) => {
    const updated = await action.run(() => api.patch<OutreachMessage>(`/api/outreach/${id}`, body));
    if (updated) { setOpen((o) => (o && o.id === id ? updated : o)); void list.reload(); }
  };
  const copy = async (m: OutreachMessage) => {
    try {
      await navigator.clipboard.writeText(`${m.subject ? `Subject: ${m.subject}\n\n` : ""}${m.body}`);
      setCopied("Copied to clipboard.");
    } catch {
      setCopied("Could not copy automatically. Select the text and copy it.");
    }
  };
  const editTemplate = (t: Template | "new") => {
    setTForm(t === "new" ? { name: "", subject: "", body: "" } : { name: t.name, subject: t.subject, body: t.body });
    setTemplate(t);
  };
  const saveTemplate = async () => {
    const ok = await action.run(() => (template === "new" ? api.post("/api/outreach/templates", tForm) : api.put(`/api/outreach/templates/${(template as Template).id}`, tForm)));
    if (ok) { setTemplate(null); void templates.reload(); }
  };

  return (
    <>
      <PageHeader title="Outreach" subtitle="Drafts are written here; a person reviews and sends them from their own email. This app never sends messages." />
      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-3 lg:col-span-2">
          <div className="flex items-center gap-3">
            <Select aria-label="Filter by status" className="max-w-52" value={status} onChange={(e) => setStatus(e.target.value)} placeholder="All statuses"
              options={["draft", "contacted", "replied", "no_reply"].map((s) => ({ value: s, label: label(s) }))} />
          </div>
          <ErrorNote error={list.error || action.error} />
          {list.loading && !list.data ? <SkeletonRows /> : !list.data?.length ? (
            <Empty title="No outreach yet" text="Open a creator and choose “Create outreach draft”." />
          ) : (
            <ul className="space-y-2">
              {list.data.map((m) => (
                <li key={m.id} className="rounded-lg border border-slate-200 bg-white p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <Link to={`/creators/${m.creator_id}`} className="font-medium text-slate-900 hover:text-indigo-700">@{m.username}</Link>
                      <Badge tone={TONE[m.status as keyof typeof TONE] ?? "slate"}>{label(m.status)}</Badge>
                      <span className="text-xs text-slate-500">{m.email ?? "no public email"}</span>
                    </div>
                    <Button small variant="secondary" onClick={() => { setCopied(""); setOpen(m); }}>Open draft</Button>
                  </div>
                  <p className="mt-1 truncate text-sm text-slate-600">{m.subject || m.body}</p>
                  <p className="mt-1 text-xs text-slate-500">
                    Created {dateTime(m.created_at)}{m.contacted_at && ` · contacted ${dateTime(m.contacted_at)}`}{m.follow_up_date && ` · follow up ${m.follow_up_date}`}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
        <Card title="Templates" action={<Button small variant="secondary" onClick={() => editTemplate("new")}>New</Button>}>
          <ul className="space-y-2">
            {(templates.data?.templates ?? []).map((t) => (
              <li key={t.id} className="flex items-center justify-between gap-2 text-sm">
                <span className="truncate text-slate-800">{t.name}</span>
                <Button small variant="ghost" onClick={() => editTemplate(t)}>Edit</Button>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-slate-500">Placeholders: {(templates.data?.placeholders ?? []).map((p) => `{${p}}`).join(" ")}</p>
        </Card>
      </div>

      {open && (
        <Modal wide title={`Draft for @${open.username}`} onClose={() => setOpen(null)}>
          <div className="space-y-3">
            <Field label="Subject"><Input aria-label="Subject" defaultValue={open.subject} onBlur={(e) => e.target.value !== open.subject && save(open.id, { subject: e.target.value })} /></Field>
            <Field label="Message"><Textarea aria-label="Message" rows={10} defaultValue={open.body} onBlur={(e) => e.target.value !== open.body && save(open.id, { body: e.target.value })} /></Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Follow-up date"><Input type="date" defaultValue={open.follow_up_date ?? ""} onChange={(e) => save(open.id, { follow_up_date: e.target.value || null })} /></Field>
              <Field label="Notes"><Input defaultValue={open.notes} onBlur={(e) => e.target.value !== open.notes && save(open.id, { notes: e.target.value })} /></Field>
            </div>
            <ErrorNote error={action.error} />
            {copied && <Notice tone="success">{copied}</Notice>}
            <div className="flex flex-wrap justify-between gap-2">
              <Button variant="secondary" onClick={() => copy(open)}>Copy to clipboard</Button>
              <span className="flex flex-wrap gap-2">
                <Button variant="secondary" disabled={action.busy || open.status === "contacted"} onClick={() => save(open.id, { status: "contacted" })}>Mark as contacted</Button>
                <Button variant="secondary" disabled={action.busy || open.status === "replied"} onClick={() => save(open.id, { status: "replied" })}>Mark as replied</Button>
                <Button variant="secondary" disabled={action.busy || open.status === "no_reply"} onClick={() => save(open.id, { status: "no_reply" })}>No reply</Button>
              </span>
            </div>
            <p className="text-xs text-slate-500">Status: {label(open.status)}. “Mark as contacted” only records that you sent it yourself.</p>
          </div>
        </Modal>
      )}
      {template && (
        <Modal wide title={template === "new" ? "New template" : "Edit template"} onClose={() => setTemplate(null)}>
          <div className="space-y-3">
            <Field label="Name"><Input value={tForm.name} onChange={(e) => setTForm({ ...tForm, name: e.target.value })} /></Field>
            <Field label="Subject"><Input value={tForm.subject} onChange={(e) => setTForm({ ...tForm, subject: e.target.value })} /></Field>
            <Field label="Body"><Textarea rows={10} value={tForm.body} onChange={(e) => setTForm({ ...tForm, body: e.target.value })} /></Field>
            <ErrorNote error={action.error} />
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setTemplate(null)}>Cancel</Button>
              <Button disabled={action.busy || !tForm.name || !tForm.body} onClick={saveTemplate}>Save template</Button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
