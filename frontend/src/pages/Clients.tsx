import { useState, type FormEvent } from "react";
import { Button, Empty, ErrorNote, Field, Input, Modal, PageHeader, Select, SkeletonRows, Table, Td, Textarea } from "../components/ui";
import { useAction, useLoad } from "../hooks/useLoad";
import { api } from "../services/api";
import type { Client } from "../types";

const EMPTY = { name: "", contact_name: "", email: "", notes: "", status: "Active" };

export function Clients() {
  const list = useLoad(() => api.get<Client[]>("/api/clients"));
  const [editing, setEditing] = useState<Client | "new" | null>(null);
  const [form, setForm] = useState(EMPTY);
  const action = useAction();

  const open = (c: Client | "new") => {
    setForm(c === "new" ? EMPTY : { name: c.name, contact_name: c.contact_name, email: c.email, notes: c.notes, status: c.status });
    action.setError("");
    setEditing(c);
  };
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const ok = await action.run(() => (editing === "new" ? api.post("/api/clients", form) : api.patch(`/api/clients/${(editing as Client).id}`, form)));
    if (ok) { setEditing(null); void list.reload(); }
  };
  const remove = async (c: Client) => {
    if (!window.confirm(`Delete client “${c.name}”?`)) return;
    if (await action.run(() => api.del(`/api/clients/${c.id}`))) void list.reload();
  };

  return (
    <>
      <PageHeader title="Clients" subtitle="Businesses we run creator research for. Each client only ever sees their own shortlists."
        action={<Button onClick={() => open("new")}>New client</Button>} />
      <div className="mb-3"><ErrorNote error={list.error || (editing ? "" : action.error)} /></div>
      {list.loading && !list.data ? <SkeletonRows /> : !list.data?.length ? (
        <Empty title="No clients yet" text="Add a client, then create campaigns for them." action={<Button onClick={() => open("new")}>New client</Button>} />
      ) : (
        <Table head={["Client", "Contact", "Email", "Campaigns", "Status", ""]}>
          {list.data.map((c) => (
            <tr key={c.id}>
              <Td className="font-medium text-slate-900">{c.name}</Td>
              <Td>{c.contact_name || "—"}</Td>
              <Td>{c.email || "—"}</Td>
              <Td className="tabular-nums">{c.campaigns}</Td>
              <Td>{c.status}</Td>
              <Td><span className="flex gap-1.5">
                <Button small variant="secondary" onClick={() => open(c)}>Edit</Button>
                <Button small variant="danger" onClick={() => remove(c)}>Delete</Button>
              </span></Td>
            </tr>
          ))}
        </Table>
      )}
      {editing && (
        <Modal title={editing === "new" ? "New client" : "Edit client"} onClose={() => setEditing(null)}>
          <form onSubmit={submit} className="space-y-3">
            <Field label="Client name"><Input aria-label="Client name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Contact person"><Input value={form.contact_name} onChange={(e) => setForm({ ...form, contact_name: e.target.value })} /></Field>
            <Field label="Email"><Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
            <Field label="Status"><Select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} options={["Active", "Paused", "Closed"]} /></Field>
            <Field label="Notes"><Textarea rows={3} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></Field>
            <ErrorNote error={action.error} />
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setEditing(null)}>Cancel</Button>
              <Button type="submit" disabled={action.busy}>Save client</Button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
