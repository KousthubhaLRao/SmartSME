import { and, eq, sql } from "drizzle-orm";
import { db } from "@/db";
import * as s from "@/db/schema";
import { publish } from "@/lib/events/publish";
import { drainQueue } from "@/worker/loop";

export interface ProductInput {
  name: string;
  sku?: string | null;
  hsn?: string | null;
  unit?: string;
  purchasePrice?: number;
  sellingPrice?: number;
  stock?: number;
  lowStockThreshold?: number;
}

export async function createProduct(businessId: string, input: ProductInput) {
  if (!input.name.trim()) throw new Error("Product name is required.");
  const [product] = await db
    .insert(s.products)
    .values({
      businessId,
      name: input.name.trim(),
      sku: input.sku || null,
      hsn: input.hsn || null,
      unit: input.unit || "pcs",
      purchasePrice: input.purchasePrice ?? 0,
      sellingPrice: input.sellingPrice ?? 0,
      stock: Math.trunc(input.stock ?? 0),
      lowStockThreshold: Math.trunc(input.lowStockThreshold ?? 10),
    })
    .returning();
  if (product.stock > 0) {
    await db.insert(s.stockMovements).values({
      businessId,
      productId: product.id,
      delta: product.stock,
      reason: "adjustment",
      note: "Opening stock",
    });
  }
  return product;
}

export async function updateProduct(businessId: string, productId: string, input: ProductInput) {
  await db
    .update(s.products)
    .set({
      name: input.name.trim(),
      sku: input.sku || null,
      hsn: input.hsn || null,
      unit: input.unit || "pcs",
      purchasePrice: input.purchasePrice ?? 0,
      sellingPrice: input.sellingPrice ?? 0,
      lowStockThreshold: Math.trunc(input.lowStockThreshold ?? 10),
    })
    .where(and(eq(s.products.id, productId), eq(s.products.businessId, businessId)));
}

// A manual stock adjustment (audit, correction, damage). Emits STOCK_UPDATED so
// the low-stock workflow re-evaluates.
export async function adjustStock(
  businessId: string,
  productId: string,
  delta: number,
  note: string,
) {
  if (!Number.isFinite(delta) || delta === 0) throw new Error("Enter a non-zero quantity.");
  await db.transaction(async (tx) => {
    await tx
      .update(s.products)
      .set({ stock: sql`${s.products.stock} + ${Math.trunc(delta)}` })
      .where(and(eq(s.products.id, productId), eq(s.products.businessId, businessId)));
    await tx.insert(s.stockMovements).values({
      businessId,
      productId,
      delta: Math.trunc(delta),
      reason: "adjustment",
      note: note || "Manual adjustment",
    });
    await publish(tx, businessId, "STOCK_UPDATED", { productId, cause: "adjustment" });
  });
  await drainQueue();
}

export async function deleteProduct(businessId: string, productId: string) {
  await db
    .delete(s.products)
    .where(and(eq(s.products.id, productId), eq(s.products.businessId, businessId)));
}
