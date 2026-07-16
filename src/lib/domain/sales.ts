import { and, count, eq, sql } from "drizzle-orm";
import { db } from "@/db";
import * as s from "@/db/schema";
import { publish } from "@/lib/events/publish";
import { paymentStatusFor } from "@/lib/workflow/engine";
import { drainQueue } from "@/worker/loop";
import { round2 } from "@/lib/utils";
import { assertPartyOwned, cleanLineItems, loadOwnedProducts } from "./line-items";

export interface SaleLineInput {
  productId?: string | null;
  description: string;
  quantity: number;
  unitPrice: number;
}

export interface CreateSaleInput {
  partyId?: string | null;
  items: SaleLineInput[];
  amountPaid?: number;
  discountType?: "none" | "amount" | "percentage";
  discountValue?: number;
  notes?: string | null;
  source?: string;
}

export interface SaleTotals {
  subtotal: number;
  discountAmount: number;
  tax: number;
  total: number;
}

export function calculateSaleTotals(subtotal: number, taxRate: number, discountType: "none" | "amount" | "percentage" = "none", discountValue = 0): SaleTotals {
  const safeSubtotal = round2(Math.max(0, subtotal));
  let discountAmount = 0;
  if (discountType === "amount") {
    discountAmount = round2(Math.max(0, discountValue));
  } else if (discountType === "percentage") {
    discountAmount = round2(safeSubtotal * Math.max(0, discountValue) / 100);
  }
  const discountedSubtotal = round2(Math.max(0, safeSubtotal - discountAmount));
  const tax = round2(discountedSubtotal * (taxRate / 100));
  const total = round2(discountedSubtotal + tax);
  return { subtotal: safeSubtotal, discountAmount, tax, total };
}

/**
 * Creates a sale using the outbox pattern: the sale rows AND the SALE_CREATED
 * event are written in the same transaction. The worker then updates inventory
 * and the customer's balance.
 */
export async function createSale(businessId: string, input: CreateSaleInput) {
  const items = cleanLineItems(input.items);
  await assertPartyOwned(businessId, input.partyId);

  // Block overselling: a sale can never take a tracked product below zero. We
  // validate stock up front so the invoice is never created for stock we don't
  // have, rather than letting the worker drive inventory negative. This also
  // rejects any productId that does not belong to the business.
  const products = await loadOwnedProducts(businessId, items);
  const wanted = new Map<string, number>();
  for (const it of items) {
    if (it.productId) wanted.set(it.productId, (wanted.get(it.productId) ?? 0) + it.quantity);
  }
  const shortfalls: string[] = [];
  for (const [id, need] of wanted) {
    const p = products.get(id)!;
    if (need > p.stock) {
      shortfalls.push(`${p.name} (in stock: ${p.stock} ${p.unit}, requested: ${need})`);
    }
  }
  if (shortfalls.length > 0) {
    const lead =
      shortfalls.length === 1
        ? "Not enough stock to complete this sale:"
        : "Not enough stock for these items:";
    throw new Error(`${lead} ${shortfalls.join("; ")}. Reduce the quantity or restock first.`);
  }

  const [biz] = await db.select().from(s.businesses).where(eq(s.businesses.id, businessId));
  const subtotal = round2(items.reduce((a, i) => a + i.quantity * i.unitPrice, 0));
  const { tax, total, discountAmount } = calculateSaleTotals(
    subtotal,
    biz.taxRate,
    input.discountType ?? "none",
    input.discountValue ?? 0,
  );
  const rawPaid = input.amountPaid ?? 0;
  if (!Number.isFinite(rawPaid)) throw new Error("Amount paid must be a valid number.");
  const amountPaid = round2(Math.max(0, Math.min(rawPaid, total)));
  const paymentStatus = paymentStatusFor(amountPaid, total);

  const [{ value }] = await db
    .select({ value: count() })
    .from(s.sales)
    .where(eq(s.sales.businessId, businessId));
  const invoiceNumber = `${biz.invoicePrefix}-${String(Number(value) + 1).padStart(4, "0")}`;

  const sale = await db.transaction(async (tx) => {
    const [row] = await tx
      .insert(s.sales)
      .values({
        businessId,
        partyId: input.partyId || null,
        invoiceNumber,
        subtotal,
        tax,
        total,
        amountPaid,
        paymentStatus,
        source: input.source || "form",
        notes: input.notes || null,
      })
      .returning();

    await tx.insert(s.saleItems).values(
      items.map((i) => ({
        saleId: row.id,
        productId: i.productId || null,
        description: i.description.trim(),
        quantity: i.quantity,
        unitPrice: i.unitPrice,
        lineTotal: round2(i.quantity * i.unitPrice),
      })),
    );

    await publish(tx, businessId, "SALE_CREATED", { saleId: row.id });
    return row;
  });

  // Process the event chain now so inventory/balances/alerts apply within this
  // request (works on serverless; on long-running hosts the interval also runs).
  await drainQueue();
  return sale;
}

// Cancel a sale: restore stock, reverse the receivable, mark it cancelled.
export async function cancelSale(businessId: string, saleId: string): Promise<void> {
  const [sale] = await db
    .select()
    .from(s.sales)
    .where(and(eq(s.sales.id, saleId), eq(s.sales.businessId, businessId)));
  if (!sale || sale.status === "cancelled") return;

  const moves = await db
    .select()
    .from(s.stockMovements)
    .where(and(eq(s.stockMovements.refId, saleId), eq(s.stockMovements.reason, "sale")));

  await db.transaction(async (tx) => {
    for (const m of moves) {
      // m.delta is negative for a sale; subtracting it adds the stock back.
      await tx
        .update(s.products)
        .set({ stock: sql`${s.products.stock} - ${m.delta}` })
        .where(eq(s.products.id, m.productId));
      await tx.insert(s.stockMovements).values({
        businessId,
        productId: m.productId,
        delta: -m.delta,
        reason: "adjustment",
        refType: "sale-cancel",
        refId: saleId,
        note: `Cancelled ${sale.invoiceNumber}`,
      });
    }
    const due = round2(sale.total - sale.amountPaid);
    if (sale.partyId && due !== 0) {
      await tx
        .update(s.parties)
        .set({ balance: sql`${s.parties.balance} - ${due}` })
        .where(eq(s.parties.id, sale.partyId));
    }
    await tx.update(s.sales).set({ status: "cancelled" }).where(eq(s.sales.id, saleId));
  });
}
