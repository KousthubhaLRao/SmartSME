export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function round2(n: number): number {
  return Math.round((n + Number.EPSILON) * 100) / 100;
}

const currencySymbols: Record<string, string> = {
  INR: "₹",
  USD: "$",
  EUR: "€",
  GBP: "£",
};

export function money(amount: number, currency = "INR"): string {
  const symbol = currencySymbols[currency] ?? "";
  const value = (amount ?? 0).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${symbol}${value}`;
}

export function compactMoney(amount: number, currency = "INR"): string {
  const symbol = currencySymbols[currency] ?? "";
  const abs = Math.abs(amount);
  if (abs >= 1_00_00_000) return `${symbol}${(amount / 1_00_00_000).toFixed(2)}Cr`;
  if (abs >= 1_00_000) return `${symbol}${(amount / 1_00_000).toFixed(2)}L`;
  if (abs >= 1_000) return `${symbol}${(amount / 1_000).toFixed(1)}K`;
  return `${symbol}${amount.toFixed(0)}`;
}

export function formatDate(d: Date | string | number): string {
  const date = new Date(d);
  return date.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function formatDateTime(d: Date | string | number): string {
  const date = new Date(d);
  return date.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function timeAgo(d: Date | string | number): string {
  const date = new Date(d).getTime();
  const diff = Date.now() - date;
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return "just now";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  return `${day}d ago`;
}

export function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : "Something went wrong.";
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");
}

/**
 * Parses a `yyyy-mm-dd` (or ISO) form value into a Date; undefined when blank
 * or unparseable. A bare `yyyy-mm-dd` would parse as UTC midnight, which can
 * land on the previous calendar day locally — so we anchor it to local noon.
 */
export function parseDateInput(value: unknown): Date | undefined {
  const raw = String(value ?? "").trim();
  if (!raw) return undefined;
  const d = /^\d{4}-\d{2}-\d{2}$/.test(raw) ? new Date(`${raw}T12:00:00`) : new Date(raw);
  return Number.isNaN(d.getTime()) ? undefined : d;
}

/** Formats a Date as `yyyy-mm-dd` for an <input type="date"> value. */
export function toDateInputValue(d: Date | string | number): string {
  const date = new Date(d);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}`;
}
