export const num = (value: number | null | undefined): string =>
  value === null || value === undefined ? "—" : value.toLocaleString("en-IN");

export const compact = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return "—";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1).replace(/\.0$/, "")}K`;
  return String(value);
};

export const inr = (value: number | null | undefined): string =>
  value === null || value === undefined ? "—" : `₹${value.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

export const usd = (value: number | null | undefined): string =>
  value === null || value === undefined ? "—" : `$${value.toLocaleString("en-US", { maximumFractionDigits: 4 })}`;

export const dateTime = (iso: string | null | undefined): string => {
  if (!iso) return "—";
  const d = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  return d.toLocaleString("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
};

export const day = (iso: string | null | undefined): string =>
  iso ? new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "—";

export const label = (text: string): string =>
  text.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase());
