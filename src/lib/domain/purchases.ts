import { and, count, eq, sql } from "drizzle-orm";
import { db } from "@/db";
import * as s from "@/db/schema";
import { publish } from "@/lib/events/publish";
import { paymentStatusFor } from "@/lib/workflow/engine";
import { drainQueue } from "@/worker/loop";
import { round2 } from "@/lib/utils";

export interface PurchaseLineInput {
  productId?: string | null;
  description: string;
  quantity: number;
  unitPrice: number;
}

export interface CreatePurchaseInput {
  partyId?: string | null;
  items: PurchaseLineInput[];
  amountPaid?: number;
  notes?: string | null;
  source?: string;
}

export async function createPurchase(businessId: string, input: CreatePurchaseInput) {
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
    .from(s.purchases)
    .where(eq(s.purchases.businessId, businessId));
  const referenceNumber = `PO-${String(Number(value) + 1).padStart(4, "0")}`;

  const pur = await db.transaction(async (tx) => {
    const [row] = await tx
      .insert(s.purchases)
      .values({
        businessId,
        partyId: input.partyId || null,
        referenceNumber,
        subtotal,
        tax,
        total,
        amountPaid,
        paymentStatus,
        source: input.source || "form",
        notes: input.notes || null,
      })
      .returning();

    await tx.insert(s.purchaseItems).values(
      items.map((i) => ({
        purchaseId: row.id,
        productId: i.productId || null,
        description: i.description.trim(),
        quantity: i.quantity,
        unitPrice: i.unitPrice,
        lineTotal: round2(i.quantity * i.unitPrice),
      })),
    );

    await publish(tx, businessId, "PURCHASE_CREATED", { purchaseId: row.id });
    return row;
  });

  await drainQueue();
  return pur;
}

// Cancel a purchase: remove the received stock, reverse the payable.
export async function cancelPurchase(businessId: string, purchaseId: string): Promise<void> {
  const [pur] = await db
    .select()
    .from(s.purchases)
    .where(and(eq(s.purchases.id, purchaseId), eq(s.purchases.businessId, businessId)));
  if (!pur || pur.status === "cancelled") return;

  const moves = await db
    .select()
    .from(s.stockMovements)
    .where(and(eq(s.stockMovements.refId, purchaseId), eq(s.stockMovements.reason, "purchase")));

  await db.transaction(async (tx) => {
    for (const m of moves) {
      await tx
        .update(s.products)
        .set({ stock: sql`${s.products.stock} - ${m.delta}` })
        .where(eq(s.products.id, m.productId));
      await tx.insert(s.stockMovements).values({
        businessId,
        productId: m.productId,
        delta: -m.delta,
        reason: "adjustment",
        refType: "purchase-cancel",
        refId: purchaseId,
        note: `Cancelled ${pur.referenceNumber}`,
      });
    }
    const due = round2(pur.total - pur.amountPaid);
    if (pur.partyId && due !== 0) {
      await tx
        .update(s.parties)
        .set({ balance: sql`${s.parties.balance} - ${due}` })
        .where(eq(s.parties.id, pur.partyId));
    }
    await tx.update(s.purchases).set({ status: "cancelled" }).where(eq(s.purchases.id, purchaseId));
  });
}
