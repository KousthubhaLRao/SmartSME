import { and, asc, eq, gte, lte } from "drizzle-orm";
import { db } from "@/db";
import * as s from "@/db/schema";
import { parseDateInput, round2 } from "@/lib/utils";

export type ReportType = "sales" | "purchases" | "expenses" | "consolidated";
export type PeriodPreset =
  | "today"
  | "week"
  | "month"
  | "last_month"
  | "quarter"
  | "half_year"
  | "year"
  | "last_12_months"
  | "custom";

export interface ReportSection {
  key: "sales" | "purchases" | "expenses";
  title: string;
  columns: string[];
  /** Column indexes holding numbers (right-aligned in the PDF). */
  numericColumns: number[];
  rows: string[][];
  count: number;
  /** Net total, excluding cancelled documents. */
  total: number;
  cancelledCount: number;
}

export interface BusinessReport {
  business: { name: string; address: string | null; gstNumber: string | null; currency: string };
  title: string;
  periodLabel: string;
  rangeLabel: string;
  generatedAt: string;
  sections: ReportSection[];
  summary: { label: string; value: string; strong?: boolean }[];
  fileName: string;
  empty: boolean;
}

const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const endOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate(), 23, 59, 59, 999);

// Plain grouped number, no currency glyph: the PDF core fonts have no rupee sign,
// so the currency code is shown in the summary and header instead.
const num = (n: number) =>
  (n ?? 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const shortDate = (d: Date | string) =>
  new Date(d).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });

export function resolvePeriod(
  preset: PeriodPreset,
  fromStr?: string,
  toStr?: string,
): { from: Date; to: Date; label: string } {
  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth();
  const d = now.getDate();

  switch (preset) {
    case "today":
      return { from: startOfDay(now), to: endOfDay(now), label: "Today" };
    case "week":
      return { from: startOfDay(new Date(y, m, d - 6)), to: endOfDay(now), label: "Last 7 days" };
    case "month":
      return { from: new Date(y, m, 1), to: endOfDay(now), label: "This month" };
    case "last_month":
      return { from: new Date(y, m - 1, 1), to: new Date(y, m, 0, 23, 59, 59, 999), label: "Last month" };
    case "quarter":
      return { from: startOfDay(new Date(y, m - 3, d)), to: endOfDay(now), label: "Last 3 months" };
    case "half_year":
      return { from: startOfDay(new Date(y, m - 6, d)), to: endOfDay(now), label: "Last 6 months" };
    case "year":
      return { from: new Date(y, 0, 1), to: endOfDay(now), label: `This year (${y})` };
    case "last_12_months":
      return { from: startOfDay(new Date(y - 1, m, d)), to: endOfDay(now), label: "Last 12 months" };
    case "custom": {
      const f = parseDateInput(fromStr);
      const t = parseDateInput(toStr);
      const from = f ? startOfDay(f) : new Date(y, m, 1);
      const to = t ? endOfDay(t) : endOfDay(now);
      // A backwards range would silently return nothing, so swap it instead.
      return from <= to ? { from, to, label: "Custom range" } : { from: to, to: from, label: "Custom range" };
    }
  }
}

const TITLES: Record<ReportType, string> = {
  sales: "Sales Report",
  purchases: "Purchases Report",
  expenses: "Expenses Report",
  consolidated: "Consolidated Business Report",
};

export async function buildReport(
  businessId: string,
  input: { type: ReportType; preset: PeriodPreset; from?: string; to?: string },
): Promise<BusinessReport> {
  const { from, to, label } = resolvePeriod(input.preset, input.from, input.to);
  const [biz] = await db.select().from(s.businesses).where(eq(s.businesses.id, businessId));
  const cur = biz.currency;
  const wantSales = input.type === "sales" || input.type === "consolidated";
  const wantPurchases = input.type === "purchases" || input.type === "consolidated";
  const wantExpenses = input.type === "expenses" || input.type === "consolidated";

  const sections: ReportSection[] = [];
  let salesTotal = 0;
  let purchasesTotal = 0;
  let expensesTotal = 0;

  if (wantSales) {
    const rows = await db
      .select({ sale: s.sales, partyName: s.parties.name })
      .from(s.sales)
      .leftJoin(s.parties, eq(s.sales.partyId, s.parties.id))
      .where(and(eq(s.sales.businessId, businessId), gte(s.sales.date, from), lte(s.sales.date, to)))
      .orderBy(asc(s.sales.date));

    let cancelled = 0;
    for (const r of rows) {
      if (r.sale.status === "cancelled") cancelled += 1;
      else salesTotal += r.sale.total;
    }
    salesTotal = round2(salesTotal);
    sections.push({
      key: "sales",
      title: "Sales",
      columns: ["Date", "Invoice", "Customer", "Subtotal", "Discount", "Tax", "Total", "Paid", "Due", "Status"],
      numericColumns: [3, 4, 5, 6, 7, 8],
      rows: rows.map(({ sale, partyName }) => [
        shortDate(sale.date),
        sale.invoiceNumber,
        partyName ?? "Walk-in",
        num(sale.subtotal),
        num(sale.discountAmount),
        num(sale.tax),
        num(sale.total),
        num(sale.amountPaid),
        num(sale.status === "cancelled" ? 0 : round2(sale.total - sale.amountPaid)),
        sale.status === "cancelled" ? "Cancelled" : sale.paymentStatus,
      ]),
      count: rows.length,
      total: salesTotal,
      cancelledCount: cancelled,
    });
  }

  if (wantPurchases) {
    const rows = await db
      .select({ purchase: s.purchases, partyName: s.parties.name })
      .from(s.purchases)
      .leftJoin(s.parties, eq(s.purchases.partyId, s.parties.id))
      .where(and(eq(s.purchases.businessId, businessId), gte(s.purchases.date, from), lte(s.purchases.date, to)))
      .orderBy(asc(s.purchases.date));

    let cancelled = 0;
    for (const r of rows) {
      if (r.purchase.status === "cancelled") cancelled += 1;
      else purchasesTotal += r.purchase.total;
    }
    purchasesTotal = round2(purchasesTotal);
    sections.push({
      key: "purchases",
      title: "Purchases",
      columns: ["Date", "Reference", "Supplier", "Subtotal", "Discount", "Tax", "Total", "Paid", "Due", "Status"],
      numericColumns: [3, 4, 5, 6, 7, 8],
      rows: rows.map(({ purchase, partyName }) => [
        shortDate(purchase.date),
        purchase.referenceNumber,
        partyName ?? "-",
        num(purchase.subtotal),
        num(purchase.discountAmount),
        num(purchase.tax),
        num(purchase.total),
        num(purchase.amountPaid),
        num(purchase.status === "cancelled" ? 0 : round2(purchase.total - purchase.amountPaid)),
        purchase.status === "cancelled" ? "Cancelled" : purchase.paymentStatus,
      ]),
      count: rows.length,
      total: purchasesTotal,
      cancelledCount: cancelled,
    });
  }

  if (wantExpenses) {
    const rows = await db
      .select()
      .from(s.expenses)
      .where(and(eq(s.expenses.businessId, businessId), gte(s.expenses.date, from), lte(s.expenses.date, to)))
      .orderBy(asc(s.expenses.date));

    expensesTotal = round2(rows.reduce((a, e) => a + e.amount, 0));
    sections.push({
      key: "expenses",
      title: "Expenses",
      columns: ["Date", "Category", "Description", "Amount"],
      numericColumns: [3],
      rows: rows.map((e) => [shortDate(e.date), e.category, e.description, num(e.amount)]),
      count: rows.length,
      total: expensesTotal,
      cancelledCount: 0,
    });
  }

  const summary: BusinessReport["summary"] = [];
  if (wantSales) summary.push({ label: "Total sales", value: `${cur} ${num(salesTotal)}` });
  if (wantPurchases) summary.push({ label: "Total purchases", value: `${cur} ${num(purchasesTotal)}` });
  if (wantExpenses) summary.push({ label: "Total expenses", value: `${cur} ${num(expensesTotal)}` });
  if (input.type === "consolidated") {
    summary.push({
      label: "Net cash (sales - purchases - expenses)",
      value: `${cur} ${num(round2(salesTotal - purchasesTotal - expensesTotal))}`,
      strong: true,
    });
  }
  for (const sec of sections) {
    summary.push({
      label: `${sec.title} recorded`,
      value: sec.cancelledCount > 0 ? `${sec.count} (${sec.cancelledCount} cancelled)` : `${sec.count}`,
    });
  }

  const pad = (n: number) => String(n).padStart(2, "0");
  const stamp = `${from.getFullYear()}${pad(from.getMonth() + 1)}${pad(from.getDate())}-${to.getFullYear()}${pad(to.getMonth() + 1)}${pad(to.getDate())}`;
  const slug = biz.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "business";

  return {
    business: { name: biz.name, address: biz.address, gstNumber: biz.gstNumber, currency: cur },
    title: TITLES[input.type],
    periodLabel: label,
    rangeLabel: `${shortDate(from)} to ${shortDate(to)}`,
    generatedAt: new Date().toLocaleString("en-IN", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }),
    sections,
    summary,
    fileName: `${slug}-${input.type}-${stamp}.pdf`,
    empty: sections.every((sec) => sec.rows.length === 0),
  };
}
