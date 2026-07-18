"use server";

import { eq } from "drizzle-orm";
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
  discountType: "none" | "amount" | "percentage";
  discountValue: number;
  note: string;
}

export type ParseResult = { draft?: Draft; error?: string };

/** Lowercase, drop punctuation, collapse whitespace — so "Anita Stores." and
 *  "ANITA  STORES" compare equal. */
function norm(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9\s]/g, " ").replace(/\s+/g, " ").trim();
}

/**
 * Fuzzy-matches an extracted name to a known party/product. Tries, in order:
 * exact (normalized), substring either direction, then token-subset (every word
 * of the shorter name appears in the other) so "Anita" resolves "Anita Stores".
 */
function bestMatch<T extends { name: string }>(list: T[], q: string | null): T | undefined {
  if (!q) return undefined;
  const needle = norm(q);
  if (!needle) return undefined;

  const exact = list.find((x) => norm(x.name) === needle);
  if (exact) return exact;

  const sub = list.find((x) => {
    const n = norm(x.name);
    return n.length > 1 && (n.includes(needle) || needle.includes(n));
  });
  if (sub) return sub;

  const nt = needle.split(" ").filter(Boolean);
  return list.find((x) => {
    const xt = norm(x.name).split(" ").filter(Boolean);
    if (!xt.length) return false;
    const [short, longSet] = nt.length <= xt.length ? [nt, new Set(xt)] : [xt, new Set(nt)];
    return short.length > 0 && short.every((t) => longSet.has(t));
  });
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
          discountType: "none",
          discountValue: 0,
          note: text.trim(),
        },
      };
    }

    // Match the party across ALL parties (not just the guessed type). A known
    // party's own type is authoritative for sale-vs-purchase, so a named
    // customer/supplier corrects a mis-guessed direction and always links.
    const allParties = await db
      .select()
      .from(sc.parties)
      .where(eq(sc.parties.businessId, business.id));
    const products = await db.select().from(sc.products).where(eq(sc.products.businessId, business.id));

    const matchedParty = bestMatch(allParties, parsed.party);
    const effectiveType: "sale" | "purchase" = matchedParty
      ? matchedParty.type === "supplier"
        ? "purchase"
        : "sale"
      : suggestedType;

    let items: DraftItem[];
    if (parsed.allInventory && effectiveType === "sale") {
      // "Sell the entire inventory" — one line per in-stock product, at its
      // full quantity and selling price. The confirm screen lets the user trim.
      const inStock = products.filter((p) => p.stock > 0);
      items = inStock.length
        ? inStock.map((p) => ({
            productId: p.id,
            description: p.name,
            quantity: p.stock,
            unitPrice: p.sellingPrice,
          }))
        : [{ productId: null, description: parsed.product ?? "Item", quantity: 1, unitPrice: 0 }];
    } else {
      const matchedProduct = bestMatch(products, parsed.product);
      const qty = parsed.quantity && parsed.quantity > 0 ? parsed.quantity : 1;
      const price = matchedProduct
        ? effectiveType === "purchase"
          ? matchedProduct.purchasePrice
          : matchedProduct.sellingPrice
        : parsed.amount && qty
          ? round2(parsed.amount / qty)
          : 0;
      items = [
        {
          productId: matchedProduct?.id ?? null,
          description: matchedProduct?.name ?? parsed.product ?? "Item",
          quantity: qty,
          unitPrice: price,
        },
      ];
    }

    return {
      draft: {
        suggestedType: effectiveType,
        engine: parsed.engine,
        partyId: matchedParty?.id ?? null,
        partyName: matchedParty?.name ?? parsed.party ?? null,
        items,
        amount: parsed.amount ?? null,
        category: null,
        discountType: parsed.discountType,
        discountValue: parsed.discountValue,
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

    // Match the named party across ALL parties, then let a confident match fix
    // the sale-vs-purchase direction (e.g. a handwritten customer name the model
    // defaulted to "purchase"). This is what makes a known customer link.
    const allParties = await db
      .select()
      .from(sc.parties)
      .where(eq(sc.parties.businessId, business.id));
    const products = await db.select().from(sc.products).where(eq(sc.products.businessId, business.id));
    const matchedParty = bestMatch(allParties, invoice.party);
    const effectiveType: "sale" | "purchase" = matchedParty
      ? matchedParty.type === "supplier"
        ? "purchase"
        : "sale"
      : invoice.docType === "purchase"
        ? "purchase"
        : "sale";

    const items: DraftItem[] = invoice.lineItems.map((li) => {
      const mp = bestMatch(products, li.product);
      const price =
        li.unitPrice != null && li.unitPrice > 0
          ? li.unitPrice
          : mp
            ? effectiveType === "purchase"
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
        suggestedType: effectiveType,
        engine: aiStatus()?.label ?? "AI",
        partyId: matchedParty?.id ?? null,
        partyName: matchedParty?.name ?? invoice.party ?? null,
        items: items.length ? items : [{ productId: null, description: "Item", quantity: 1, unitPrice: 0 }],
        amount: invoice.total ?? null,
        category: null,
        discountType: "none",
        discountValue: 0,
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
    const discountType = (String(formData.get("discountType") ?? "none") as "none" | "amount" | "percentage") || "none";
    const discountValue = Number(formData.get("discountValue") ?? 0);

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
      const pur = await createPurchase(business.id, { partyId, items, amountPaid, discountType, discountValue, source });
      revalidatePath("/purchases");
      revalidatePath("/dashboard");
      return { ok: `Purchase ${pur.referenceNumber} created.` };
    }
    const sale = await createSale(business.id, { partyId, items, amountPaid, discountType, discountValue, source });
    revalidatePath("/sales");
    revalidatePath("/dashboard");
    return { ok: `Sale ${sale.invoiceNumber} created.` };
  } catch (e) {
    return { error: e instanceof Error ? e.message : "Could not publish." };
  }
}
