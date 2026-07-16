"use server";

import { revalidatePath } from "next/cache";
import { and, eq } from "drizzle-orm";
import { db } from "@/db";
import * as sc from "@/db/schema";
import { requireUser } from "@/lib/auth/current-user";
import { createSale, cancelSale, type SaleLineInput } from "@/lib/domain/sales";
import { recordPayment } from "@/lib/domain/payments";
import { errMsg } from "@/lib/utils";

export interface ActionResult {
  error?: string;
}

export interface SaleDetail {
  sale: sc.Sale;
  party: { name: string; phone: string | null; gstNumber: string | null } | null;
  items: Array<{ id: string; description: string; quantity: number; unitPrice: number; lineTotal: number }>;
}

/** Loads one sale with its party and line items, for the row-click detail modal. */
export async function loadSaleDetailAction(
  saleId: string,
): Promise<{ detail?: SaleDetail; error?: string }> {
  const { business } = await requireUser();
  try {
    const [sale] = await db
      .select()
      .from(sc.sales)
      .where(and(eq(sc.sales.id, saleId), eq(sc.sales.businessId, business.id)));
    if (!sale) return { error: "Sale not found." };

    const party = sale.partyId
      ? (await db.select().from(sc.parties).where(eq(sc.parties.id, sale.partyId)))[0]
      : undefined;
    const items = await db.select().from(sc.saleItems).where(eq(sc.saleItems.saleId, sale.id));

    return {
      detail: {
        sale,
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

export async function createSaleAction(formData: FormData): Promise<ActionResult> {
  const { business } = await requireUser();
  try {
    const partyId = String(formData.get("partyId") ?? "") || null;
    const items = JSON.parse(String(formData.get("items") ?? "[]")) as SaleLineInput[];
    const amountPaid = Number(formData.get("amountPaid") ?? 0);
    const discountType = (String(formData.get("discountType") ?? "none") as "none" | "amount" | "percentage") || "none";
    const discountValue = Number(formData.get("discountValue") ?? 0);
    const notes = String(formData.get("notes") ?? "") || null;
    await createSale(business.id, { partyId, items, amountPaid, discountType, discountValue, notes, source: "form" });
    revalidatePath("/sales");
    revalidatePath("/dashboard");
    return {};
  } catch (e) {
    return { error: errMsg(e) };
  }
}

export async function recordSalePaymentAction(formData: FormData): Promise<ActionResult> {
  const { business } = await requireUser();
  try {
    const saleId = String(formData.get("saleId") ?? "");
    const amount = Number(formData.get("amount") ?? 0);
    await recordPayment(business.id, { saleId, amount });
    revalidatePath("/sales");
    revalidatePath("/dashboard");
    return {};
  } catch (e) {
    return { error: errMsg(e) };
  }
}

export async function cancelSaleAction(saleId: string): Promise<ActionResult> {
  const { business } = await requireUser();
  try {
    await cancelSale(business.id, saleId);
    revalidatePath("/sales");
    revalidatePath("/dashboard");
    return {};
  } catch (e) {
    return { error: errMsg(e) };
  }
}
