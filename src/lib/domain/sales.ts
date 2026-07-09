import { and, count, eq, sql } from "drizzle-orm";
import { db } from "@/db";
import * as s from "@/db/schema";
import { publish } from "@/lib/events/publish";
import { paymentStatusFor } from "@/lib/workflow/engine";
import { drainQueue } from "@/worker/loop";
import { round2 } from "@/lib/utils";

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
  notes?: string | null;
  source?: string;
}

/**
 * Creates a sale using the outbox pattern: the sale rows AND the SALE_CREATED
 * event are written in the same transaction. The worker then updates inventory
 * and the customer's balance.
 */
export async function createSale(businessId: string, input: CreateSaleInput) {
  const items = input.items.filter((i) => (i.description ?? "").trim() && i.quantity > 0);
  if (items.length === 0) throw new Error("Add at least one line item.");

  const [biz] = await db.select().from(s.businesses).where(eq(s.businesses.id, businessId));
  const subtotal = round2(items.reduce((a, i) => a + i.quantity * i.unitPrice, 0));
  const tax = round2(subtotal * (biz.taxRate / 100));
  const total = round2(subtotal + tax);
  const amountPaid = round2(Math.max(0, Math.min(input.amountPaid ?? 0, total)));
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
