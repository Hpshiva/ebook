import { useState, type FormEvent } from "react";
import { Badge, Button, DemoBadge, Empty, ErrorNote, Field, Input, Modal, Notice, PageHeader, Select, SkeletonRows, Stat, Table, Td } from "../components/ui";
import { useAction, useLoad } from "../hooks/useLoad";
import { api } from "../services/api";
import type { Creator, Paged, Partnership } from "../types";
import { inr } from "../utils/format";

interface Product { id: number; name: string; price: number }
interface Listing { items: Partnership[]; totals: Record<string, number> }
const EMPTY = {
  creator_id: "", product_id: "", start_date: "", commission_pct: "30", fixed_payment: "0", tracking_url: "", promo_code: "",
  clicks: "", conversions: "", revenue: "0", amount_paid: "0", payment_status: "pending", notes: "",
};

export function Partnerships() {
  const list = useLoad(() => api.get<Listing>("/api/partnerships"));
  const products = useLoad(() => api.get<Product[]>("/api/products"));
  const creators = useLoad(() => api.get<Paged<Creator>>("/api/creators", { page_size: 200, sort: "username", order: "asc" }));
  const [editing, setEditing] = useState<Partnership | "new" | null>(null);
  const [form, setForm] = useState(EMPTY);
  const [productName, setProductName] = useState("");
  const action = useAction();
  const set = (patch: Partial<typeof EMPTY>) => setForm((f) => ({ ...f, ...patch }));

  const open = (p: Partnership | "new") => {
    action.setError("");
    setForm(p === "new" ? EMPTY : {
      creator_id: String(p.creator_id), product_id: String(p.product_id), start_date: p.start_date ?? "", commission_pct: String(p.commission_pct),
      fixed_payment: String(p.fixed_payment), tracking_url: p.tracking_url, promo_code: p.promo_code, clicks: p.clicks === null ? "" : String(p.clicks),
      conversions: p.conversions === null ? "" : String(p.conversions), revenue: String(p.revenue), amount_paid: String(p.amount_paid),
      payment_status: p.payment_status, notes: p.notes,
    });
    setEditing(p);
  };
  const addProduct = async () => {
    const p = await action.run(() => api.post<Product>("/api/products", { name: productName }));
    if (p) { setProductName(""); await products.reload(); set({ product_id: String(p.id) }); }
  };
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const n = (v: string) => (v === "" ? null : Number(v));
    const body = {
      ...form, creator_id: Number(form.creator_id), product_id: Number(form.product_id), start_date: form.start_date || null,
      commission_pct: Number(form.commission_pct), fixed_payment: Number(form.fixed_payment), clicks: n(form.clicks),
      conversions: n(form.conversions), revenue: Number(form.revenue), amount_paid: Number(form.amount_paid),
    };
    const ok = await action.run(() => (editing === "new" ? api.post("/api/partnerships", body) : api.put(`/api/partnerships/${(editing as Partnership).id}`, body)));
    if (ok) { setEditing(null); void list.reload(); }
  };
  const preview = Number(form.revenue || 0) * Number(form.commission_pct || 0) / 100 + Number(form.fixed_payment || 0);
  const t = list.data?.totals;

  return (
    <>
      <PageHeader title="Partnerships" subtitle="Revenue-share deals with creators for our own digital products."
        action={<Button onClick={() => open("new")}>New partnership</Button>} />
      {t && (
        <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="Revenue" value={inr(t.revenue)} />
          <Stat label="Commission total" value={inr(t.commission_total)} />
          <Stat label="Commission owed" value={inr(t.commission_owed)} tone={t.commission_owed ? "amber" : undefined} />
          <Stat label="Net revenue" value={inr(t.net_revenue)} tone="green" />
        </div>
      )}
      <ErrorNote error={list.error} />
      {list.loading && !list.data ? <SkeletonRows /> : !list.data?.items.length ? (
        <Empty title="No partnerships yet" text="Record a deal once a creator agrees to promote a product." action={<Button onClick={() => open("new")}>New partnership</Button>} />
      ) : (
        <Table head={["Creator", "Product", "Commission", "Promo code", "Conversions", "Revenue", "Owed", "Payment", ""]}>
          {list.data.items.map((p) => (
            <tr key={p.id}>
              <Td><span className="flex items-center gap-1.5 font-medium text-slate-900">@{p.username} {p.is_demo && <DemoBadge />}</span></Td>
              <Td>{p.product_name}</Td>
              <Td className="tabular-nums">{p.commission_pct}%{p.fixed_payment ? ` + ${inr(p.fixed_payment)}` : ""}</Td>
              <Td>{p.promo_code || "—"}</Td>
              <Td className="tabular-nums">{p.conversions ?? "—"}</Td>
              <Td className="tabular-nums">{inr(p.revenue)}</Td>
              <Td className="tabular-nums">{inr(p.commission_owed)}</Td>
              <Td><Badge tone={p.payment_status === "paid" ? "green" : p.payment_status === "partial" ? "amber" : "slate"}>{p.payment_status}</Badge></Td>
              <Td><Button small variant="secondary" onClick={() => open(p)}>Edit</Button></Td>
            </tr>
          ))}
        </Table>
      )}
      {editing && (
        <Modal wide title={editing === "new" ? "New partnership" : "Edit partnership"} onClose={() => setEditing(null)}>
          <form onSubmit={submit} className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Creator">
                <Select aria-label="Creator" required value={form.creator_id} onChange={(e) => set({ creator_id: e.target.value })} placeholder="Choose a creator"
                  options={(creators.data?.items ?? []).map((c) => ({ value: c.id, label: `@${c.username}${c.is_demo ? " (demo)" : ""}` }))} />
              </Field>
              <Field label="Product">
                <Select aria-label="Product" required value={form.product_id} onChange={(e) => set({ product_id: e.target.value })} placeholder="Choose a product"
                  options={(products.data ?? []).map((p) => ({ value: p.id, label: p.name }))} />
              </Field>
            </div>
            <div className="flex items-end gap-2">
              <div className="flex-1"><Field label="Add a new product"><Input aria-label="New product name" value={productName} onChange={(e) => setProductName(e.target.value)} placeholder="e.g. Fitness PDF guide" /></Field></div>
              <Button variant="secondary" disabled={!productName.trim() || action.busy} onClick={addProduct}>Add product</Button>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Commission %"><Input aria-label="Commission %" type="number" min={0} max={100} step="0.1" value={form.commission_pct} onChange={(e) => set({ commission_pct: e.target.value })} /></Field>
              <Field label="Fixed payment (₹)"><Input type="number" min={0} value={form.fixed_payment} onChange={(e) => set({ fixed_payment: e.target.value })} /></Field>
              <Field label="Start date"><Input type="date" value={form.start_date} onChange={(e) => set({ start_date: e.target.value })} /></Field>
              <Field label="Promo code"><Input value={form.promo_code} onChange={(e) => set({ promo_code: e.target.value })} /></Field>
              <Field label="Tracking URL"><Input value={form.tracking_url} onChange={(e) => set({ tracking_url: e.target.value })} /></Field>
              <Field label="Clicks"><Input type="number" min={0} value={form.clicks} onChange={(e) => set({ clicks: e.target.value })} placeholder="if known" /></Field>
              <Field label="Conversions"><Input type="number" min={0} value={form.conversions} onChange={(e) => set({ conversions: e.target.value })} placeholder="if known" /></Field>
              <Field label="Revenue (₹)"><Input aria-label="Revenue" type="number" min={0} value={form.revenue} onChange={(e) => set({ revenue: e.target.value })} /></Field>
              <Field label="Amount paid (₹)"><Input type="number" min={0} value={form.amount_paid} onChange={(e) => set({ amount_paid: e.target.value })} /></Field>
              <Field label="Payment status"><Select value={form.payment_status} onChange={(e) => set({ payment_status: e.target.value })} options={["pending", "partial", "paid"]} /></Field>
            </div>
            <Notice>Commission at these numbers: <strong>{inr(Math.round(preview * 100) / 100)}</strong> (revenue × commission % + fixed payment).</Notice>
            <ErrorNote error={action.error} />
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setEditing(null)}>Cancel</Button>
              <Button type="submit" disabled={action.busy}>Save partnership</Button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
