"use server";

import { and, eq } from "drizzle-orm";
import { revalidatePath } from "next/cache";
import { db } from "@/db";
import * as sc from "@/db/schema";
import { requireUser } from "@/lib/auth/current-user";
import { parseCommand } from "@/lib/ai/nlp";
import { parseInvoiceImage } from "@/lib/ai/ocr";
import { createSale, type SaleLineInput } from "@/lib/domain/sales";
import { createPurchase, type PurchaseLineInput } from "@/lib/domain/purchases";
import { createExpense } from "@/lib/domain/expenses";
import { aiStatus } from "@/lib/ai/client";
import { round2 } from "@/lib/utils";

export interface DraftItem {
  productId: string | null;
  description: string;
  quantity: number;
  unitPrice: number;
}

export interface Draft {
  suggestedType: "sale" | "purchase" | "expense";
  engine: string;
  partyId: string | null;
  partyName: string | null;
  items: DraftItem[];
  amount: number | null;
  category: string | null;
  note: string;
}

export type ParseResult = { draft?: Draft; error?: string };

function fuzzyFind<T extends { name: string }>(list: T[], q: string | null): T | undefined {
  if (!q) return undefined;
  const needle = q.trim().toLowerCase();
  if (!needle) return undefined;
  return (
    list.find((x) => x.name.toLowerCase() === needle) ??
    list.find((x) => x.name.toLowerCase().includes(needle) || needle.includes(x.name.toLowerCase()))
  );
}

export async function parseTextAction(text: string): Promise<ParseResult> {
  const { business } = await requireUser();
  if (!text.trim()) return { error: "Type a command first." };
  try {
    const parsed = await parseCommand(text);
    const suggestedType =
      parsed.eventType === "PURCHASE_CREATED"
        ? "purchase"
        : parsed.eventType === "EXPENSE_ADDED"
          ? "expense"
          : "sale";

    if (suggestedType === "expense") {
      return {
        draft: {
          suggestedType,
          engine: parsed.engine,
          partyId: null,
          partyName: null,
          items: [],
          amount: parsed.amount ?? null,
          category: parsed.category ?? "General",
          note: text.trim(),
        },
      };
    }

    const parties = await db
      .select()
      .from(sc.parties)
      .where(
        and(
          eq(sc.parties.businessId, business.id),
          eq(sc.parties.type, suggestedType === "purchase" ? "supplier" : "customer"),
        ),
      );
    const products = await db.select().from(sc.products).where(eq(sc.products.businessId, business.id));

    const matchedParty = fuzzyFind(parties, parsed.party);
    const matchedProduct = fuzzyFind(products, parsed.product);
    const qty = parsed.quantity && parsed.quantity > 0 ? parsed.quantity : 1;
    const price = matchedProduct
      ? suggestedType === "purchase"
        ? matchedProduct.purchasePrice
        : matchedProduct.sellingPrice
      : parsed.amount && qty
        ? round2(parsed.amount / qty)
        : 0;

    return {
      draft: {
        suggestedType,
        engine: parsed.engine,
        partyId: matchedParty?.id ?? null,
        partyName: parsed.party ?? null,
        items: [
          {
            productId: matchedProduct?.id ?? null,
            description: matchedProduct?.name ?? parsed.product ?? "Item",
            quantity: qty,
            unitPrice: price,
          },
        ],
        amount: parsed.amount ?? null,
        category: null,
        note: text.trim(),
      },
    };
  } catch (e) {
    return { error: e instanceof Error ? e.message : "Could not parse that." };
  }
}

export async function parseImageAction(dataUrl: string): Promise<ParseResult> {
  const { business } = await requireUser();
  try {
    const match = /^data:(image\/(png|jpeg|jpg|webp|gif));base64,(.+)$/.exec(dataUrl);
    if (!match) return { error: "Unsupported image. Use PNG, JPEG, WebP, or GIF." };
    const media = (match[1] === "image/jpg" ? "image/jpeg" : match[1]) as
      | "image/png"
      | "image/jpeg"
      | "image/webp"
      | "image/gif";
    const base64 = match[3];

    const invoice = await parseInvoiceImage(base64, media);
    const suggestedType = invoice.docType === "purchase" ? "purchase" : "sale";

    const parties = await db
      .select()
      .from(sc.parties)
      .where(
        and(
          eq(sc.parties.businessId, business.id),
          eq(sc.parties.type, suggestedType === "purchase" ? "supplier" : "customer"),
        ),
      );
    const products = await db.select().from(sc.products).where(eq(sc.products.businessId, business.id));
    const matchedParty = fuzzyFind(parties, invoice.party);

    const items: DraftItem[] = invoice.lineItems.map((li) => {
      const mp = fuzzyFind(products, li.product);
      const price =
        li.unitPrice != null && li.unitPrice > 0
          ? li.unitPrice
          : mp
            ? suggestedType === "purchase"
              ? mp.purchasePrice
              : mp.sellingPrice
            : 0;
      return {
        productId: mp?.id ?? null,
        description: mp?.name ?? li.product,
        quantity: li.quantity > 0 ? li.quantity : 1,
        unitPrice: price,
      };
    });

    return {
      draft: {
        suggestedType,
        engine: aiStatus()?.label ?? "AI",
        partyId: matchedParty?.id ?? null,
        partyName: invoice.party ?? null,
        items: items.length ? items : [{ productId: null, description: "Item", quantity: 1, unitPrice: 0 }],
        amount: invoice.total ?? null,
        category: null,
        note: "Extracted from image",
      },
    };
  } catch (e) {
    return { error: e instanceof Error ? e.message : "Could not read that image." };
  }
}

export async function publishDraftAction(formData: FormData): Promise<{ error?: string; ok?: string }> {
  const { business } = await requireUser();
  try {
    const type = String(formData.get("type") ?? "sale");
    const source = String(formData.get("source") ?? "nlp");
    const partyId = String(formData.get("partyId") ?? "") || null;
    const amountPaid = Number(formData.get("amountPaid") ?? 0);

    if (type === "expense") {
      await createExpense(business.id, {
        category: String(formData.get("category") ?? "General"),
        description: String(formData.get("description") ?? ""),
        amount: Number(formData.get("amount") ?? 0),
        source,
      });
      revalidatePath("/expenses");
      revalidatePath("/dashboard");
      return { ok: "Expense recorded." };
    }

    const items = JSON.parse(String(formData.get("items") ?? "[]")) as SaleLineInput[] | PurchaseLineInput[];
    if (type === "purchase") {
      const pur = await createPurchase(business.id, { partyId, items, amountPaid, source });
      revalidatePath("/purchases");
      revalidatePath("/dashboard");
      return { ok: `Purchase ${pur.referenceNumber} created.` };
    }
    const sale = await createSale(business.id, { partyId, items, amountPaid, source });
    revalidatePath("/sales");
    revalidatePath("/dashboard");
    return { ok: `Sale ${sale.invoiceNumber} created.` };
  } catch (e) {
    return { error: e instanceof Error ? e.message : "Could not publish." };
  }
}
