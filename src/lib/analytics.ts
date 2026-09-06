import { and, eq, ne } from "drizzle-orm";
import { db } from "@/db";
import * as s from "@/db/schema";
import { round2 } from "@/lib/utils";

export function calculateOutstandingTotal<T extends { total: number; amountPaid: number }>(rows: T[]): number {
  return round2(rows.reduce((acc, row) => acc + Math.max(0, row.total - row.amountPaid), 0));
}

function clamp(n: number, lo = 0, hi = 100): number {
  return Math.max(lo, Math.min(hi, Math.round(n)));
}

export interface Overview {
  totals: {
    sales: number;
    purchases: number;
    expenses: number;
    receivable: number;
    payable: number;
    inventoryValue: number;
    grossProfit: number;
    salesCount: number;
  };
  revenueSeries: { label: string; value: number }[];
  topProducts: { label: string; value: number; display: string }[];
  topCustomers: { label: string; value: number; display: string }[];
  expenseByCategory: { label: string; value: number; display: string }[];
  lowStock: s.Product[];
  health: {
    overall: number;
    inventory: number;
    revenue: number;
    expense: number;
    cashFlow: number;
  };
}

export async function loadOverview(businessId: string, days = 14): Promise<Overview> {
  const [sales, purchases, expenses, products, parties, saleItemRows] = await Promise.all([
    db.select().from(s.sales).where(and(eq(s.sales.businessId, businessId), ne(s.sales.status, "cancelled"))),
    db.select().from(s.purchases).where(and(eq(s.purchases.businessId, businessId), ne(s.purchases.status, "cancelled"))),
    db.select().from(s.expenses).where(eq(s.expenses.businessId, businessId)),
    db.select().from(s.products).where(eq(s.products.businessId, businessId)),
    db.select().from(s.parties).where(eq(s.parties.businessId, businessId)),
    db
      .select({ item: s.saleItems, saleStatus: s.sales.status, partyId: s.sales.partyId, total: s.sales.total })
      .from(s.saleItems)
      .innerJoin(s.sales, eq(s.saleItems.saleId, s.sales.id))
      .where(and(eq(s.sales.businessId, businessId), ne(s.sales.status, "cancelled"))),
  ]);

  const totalSales = round2(sales.reduce((a, x) => a + x.total, 0));
  const totalPurchases = round2(purchases.reduce((a, x) => a + x.total, 0));
  const totalExpenses = round2(expenses.reduce((a, x) => a + x.amount, 0));
  const receivableFromSales = calculateOutstandingTotal(sales);
  const receivableFromParties = round2(
    parties.filter((p) => p.type === "customer" && p.balance > 0).reduce((a, p) => a + p.balance, 0),
  );
  const receivable = round2(receivableFromSales + receivableFromParties);
  const payable = round2(
    parties.filter((p) => p.type === "supplier" && p.balance > 0).reduce((a, p) => a + p.balance, 0),
  );
  const inventoryValue = round2(products.reduce((a, p) => a + p.stock * p.purchasePrice, 0));

  // Gross profit estimate = sold-quantity revenue minus its cost of goods.
  let cogs = 0;
  const productById = new Map(products.map((p) => [p.id, p]));
  for (const r of saleItemRows) {
    const p = r.item.productId ? productById.get(r.item.productId) : undefined;
    cogs += (p?.purchasePrice ?? 0) * r.item.quantity;
  }
  const grossProfit = round2(totalSales - cogs);

  // Daily revenue for the last `days` days.
  const now = new Date();
  const dayMs = 86_400_000;
  const buckets: { label: string; value: number; start: number }[] = [];
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() - i);
    buckets.push({ label: `${d.getDate()}`, value: 0, start: d.getTime() });
  }
  for (const sale of sales) {
    const t = new Date(sale.date).getTime();
    const idx = buckets.findIndex((b, i) => t >= b.start && (i === buckets.length - 1 || t < buckets[i + 1].start));
    if (idx >= 0) buckets[idx].value = round2(buckets[idx].value + sale.total);
  }
  const revenueSeries = buckets.map((b) => ({ label: b.label, value: b.value }));

  // Top products by revenue.
  const prodAgg = new Map<string, number>();
  for (const r of saleItemRows) {
    const key = r.item.description;
    prodAgg.set(key, (prodAgg.get(key) ?? 0) + r.item.lineTotal);
  }
  const topProducts = [...prodAgg.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([label, value]) => ({ label, value, display: fmt(value) }));

  // Top customers by sales total.
  const custAgg = new Map<string, number>();
  const partyNameById = new Map(parties.map((p) => [p.id, p.name]));
  for (const sale of sales) {
    if (!sale.partyId) continue;
    custAgg.set(sale.partyId, (custAgg.get(sale.partyId) ?? 0) + sale.total);
  }
  const topCustomers = [...custAgg.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([id, value]) => ({ label: partyNameById.get(id) ?? "Unknown", value, display: fmt(value) }));

  // Expense by category.
  const catAgg = new Map<string, number>();
  for (const e of expenses) catAgg.set(e.category, (catAgg.get(e.category) ?? 0) + e.amount);
  const expenseByCategory = [...catAgg.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([label, value]) => ({ label, value, display: fmt(value) }));

  const lowStock = products
    .filter((p) => p.stock <= p.lowStockThreshold)
    .sort((a, b) => a.stock - b.stock);

  // ---- Business health (heuristic 0-100) ----
  const healthyStock = products.filter((p) => p.stock > p.lowStockThreshold).length;
  const inventory = products.length === 0 ? 100 : clamp((healthyStock / products.length) * 100);

  const cutoff = now.getTime() - days * dayMs;
  const priorCutoff = now.getTime() - 2 * days * dayMs;
  const recentRev = sales.filter((x) => new Date(x.date).getTime() >= cutoff).reduce((a, x) => a + x.total, 0);
  const priorRev = sales
    .filter((x) => {
      const t = new Date(x.date).getTime();
      return t >= priorCutoff && t < cutoff;
    })
    .reduce((a, x) => a + x.total, 0);
  const growth = priorRev > 0 ? (recentRev - priorRev) / priorRev : recentRev > 0 ? 1 : 0;
  const revenue = clamp(60 + growth * 40, 10, 100);

  const expenseRatio = totalSales > 0 ? totalExpenses / totalSales : totalExpenses > 0 ? 1 : 0;
  const expense = clamp(100 - expenseRatio * 100, 10, 100);

  const cashFlow = payable + receivable === 0 ? 80 : clamp(40 + (receivable / (payable + receivable)) * 55, 10, 100);

  const overall = clamp((inventory + revenue + expense + cashFlow) / 4);

  return {
    totals: {
      sales: totalSales,
      purchases: totalPurchases,
      expenses: totalExpenses,
      receivable,
      payable,
      inventoryValue,
      grossProfit,
      salesCount: sales.length,
    },
    revenueSeries,
    topProducts,
    topCustomers,
    expenseByCategory,
    lowStock,
    health: { overall, inventory, revenue, expense, cashFlow },
  };
}

function fmt(n: number): string {
  return `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

export interface RevenuePoint {
  /** Short label for the x-axis. */
  label: string;
  value: number;
  /** Fuller label shown in the hover tooltip. */
  full: string;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/**
 * Revenue over the last `days`, bucketed to keep the point count readable:
 * daily up to ~a month, weekly up to ~3 months, then whole calendar months.
 */
export async function getRevenueSeries(businessId: string, days: number): Promise<RevenuePoint[]> {
  const sales = await db
    .select({ date: s.sales.date, total: s.sales.total })
    .from(s.sales)
    .where(and(eq(s.sales.businessId, businessId), ne(s.sales.status, "cancelled")));

  const now = new Date();
  const oneDay = 86_400_000;
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const endExclusive = startOfToday + oneDay;

  type Bucket = { start: number; end: number; value: number; label: string; full: string };
  const buckets: Bucket[] = [];

  if (days <= 31) {
    for (let i = days - 1; i >= 0; i--) {
      const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() - i);
      const start = d.getTime();
      buckets.push({
        start,
        end: start + oneDay,
        value: 0,
        label: `${d.getDate()}`,
        full: `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`,
      });
    }
  } else if (days <= 92) {
    const weeks = Math.ceil(days / 7);
    for (let b = weeks - 1; b >= 0; b--) {
      const end = endExclusive - b * 7 * oneDay;
      const start = end - 7 * oneDay;
      const sd = new Date(start);
      buckets.push({
        start,
        end,
        value: 0,
        label: `${sd.getDate()} ${MONTHS[sd.getMonth()]}`,
        full: `Week of ${sd.getDate()} ${MONTHS[sd.getMonth()]} ${sd.getFullYear()}`,
      });
    }
  } else {
    const months = days >= 330 ? 12 : Math.max(1, Math.round(days / 30));
    for (let m = months - 1; m >= 0; m--) {
      const d = new Date(now.getFullYear(), now.getMonth() - m, 1);
      buckets.push({
        start: d.getTime(),
        end: new Date(d.getFullYear(), d.getMonth() + 1, 1).getTime(),
        value: 0,
        label: MONTHS[d.getMonth()],
        full: `${MONTHS[d.getMonth()]} ${d.getFullYear()}`,
      });
    }
  }

  for (const sale of sales) {
    const t = new Date(sale.date).getTime();
    const bk = buckets.find((bb) => t >= bb.start && t < bb.end);
    if (bk) bk.value = round2(bk.value + sale.total);
  }

  return buckets.map((b) => ({ label: b.label, value: b.value, full: b.full }));
}
