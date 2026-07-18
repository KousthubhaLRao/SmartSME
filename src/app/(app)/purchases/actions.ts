"use server";

import { revalidatePath } from "next/cache";
import { and, eq } from "drizzle-orm";
import { db } from "@/db";
import * as sc from "@/db/schema";
import { requireUser } from "@/lib/auth/current-user";
import { createPurchase, cancelPurchase, type PurchaseLineInput } from "@/lib/domain/purchases";
import { recordPayment } from "@/lib/domain/payments";
import { errMsg } from "@/lib/utils";

export interface ActionResult {
  error?: string;
}

export interface PurchaseDetail {
  purchase: sc.Purchase;
  party: { name: string; phone: string | null; gstNumber: string | null } | null;
  items: Array<{ id: string; description: string; quantity: number; unitPrice: number; lineTotal: number }>;
}

/** Loads one purchase with its supplier and line items, for the row-click detail modal. */
export async function loadPurchaseDetailAction(
  purchaseId: string,
): Promise<{ detail?: PurchaseDetail; error?: string }> {
  const { business } = await requireUser();
  try {
    const [purchase] = await db
      .select()
      .from(sc.purchases)
      .where(and(eq(sc.purchases.id, purchaseId), eq(sc.purchases.businessId, business.id)));
    if (!purchase) return { error: "Purchase not found." };

    const party = purchase.partyId
      ? (await db.select().from(sc.parties).where(eq(sc.parties.id, purchase.partyId)))[0]
      : undefined;
    const items = await db
      .select()
      .from(sc.purchaseItems)
      .where(eq(sc.purchaseItems.purchaseId, purchase.id));

    return {
      detail: {
        purchase,
        party: party ? { name: party.name, phone: party.phone, gstNumber: party.gstNumber } : null,
        items: items.map((it) => ({
          id: it.id,
          description: it.description,
          quantity: it.quantity,
          unitPrice: it.unitPrice,
          lineTotal: it.lineTotal,
        })),
      },
    };
  } catch (e) {
    return { error: errMsg(e) };
  }
}

export async function createPurchaseAction(formData: FormData): Promise<ActionResult> {
  const { business } = await requireUser();
  try {
    const partyId = String(formData.get("partyId") ?? "") || null;
    const items = JSON.parse(String(formData.get("items") ?? "[]")) as PurchaseLineInput[];
    const amountPaid = Number(formData.get("amountPaid") ?? 0);
    const discountType = (String(formData.get("discountType") ?? "none") as "none" | "amount" | "percentage") || "none";
    const discountValue = Number(formData.get("discountValue") ?? 0);
    const notes = String(formData.get("notes") ?? "") || null;
    await createPurchase(business.id, { partyId, items, amountPaid, discountType, discountValue, notes, source: "form" });
    revalidatePath("/purchases");
    revalidatePath("/dashboard");
    return {};
  } catch (e) {
    return { error: errMsg(e) };
  }
}

export async function recordPurchasePaymentAction(formData: FormData): Promise<ActionResult> {
  const { business } = await requireUser();
  try {
    const purchaseId = String(formData.get("purchaseId") ?? "");
    const amount = Number(formData.get("amount") ?? 0);
    await recordPayment(business.id, { purchaseId, amount });
    revalidatePath("/purchases");
    revalidatePath("/dashboard");
    return {};
  } catch (e) {
    return { error: errMsg(e) };
  }
}

export async function cancelPurchaseAction(purchaseId: string): Promise<ActionResult> {
  const { business } = await requireUser();
  try {
    await cancelPurchase(business.id, purchaseId);
    revalidatePath("/purchases");
    revalidatePath("/dashboard");
    return {};
  } catch (e) {
    return { error: errMsg(e) };
  }
}
