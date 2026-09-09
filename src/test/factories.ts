import "./env"; // must be first: forces the in-memory DB before "@/db" loads
import { and, eq } from "drizzle-orm";
import { db } from "@/db";
import * as s from "@/db/schema";
import { defaultRules } from "@/lib/workflow/defaults";

/**
 * Lightweight builders for the entities tests need. Keep them small and explicit
 * so a test reads top-to-bottom. Add new builders here as the schema grows.
 */

export interface MakeBusinessOptions {
  name?: string;
  taxRate?: number;
  currency?: string;
  invoicePrefix?: string;
  /** Insert the standard workflow rule set (inventory, restock alert, flag expense, unpaid reminder). */
  withDefaultRules?: boolean;
}

export async function makeBusiness(opts: MakeBusinessOptions = {}) {
  const [biz] = await db
    .insert(s.businesses)
    .values({
      name: opts.name ?? "Test Traders",
      currency: opts.currency ?? "INR",
      taxRate: opts.taxRate ?? 18,
      invoicePrefix: opts.invoicePrefix ?? "INV",
    })
    .returning();
  if (opts.withDefaultRules) {
    await db.insert(s.workflowRules).values(defaultRules(biz.id));
  }
  return biz;
}

export async function makeCustomer(businessId: string, name = "Kumar Traders", openingBalance = 0) {
  const [p] = await db
    .insert(s.parties)
    .values({ businessId, type: "customer", name, balance: openingBalance })
    .returning();
  return p;
}

export async function makeSupplier(businessId: string, name = "ABC Suppliers", openingBalance = 0) {
  const [p] = await db
    .insert(s.parties)
    .values({ businessId, type: "supplier", name, balance: openingBalance })
    .returning();
  return p;
}

export interface MakeProductOptions {
  name?: string;
  unit?: string;
  purchasePrice?: number;
  sellingPrice?: number;
  stock?: number;
  lowStockThreshold?: number;
}

export async function makeProduct(businessId: string, overrides: MakeProductOptions = {}) {
  const [p] = await db
    .insert(s.products)
    .values({
      businessId,
      name: overrides.name ?? "Rice Bag 25kg",
      unit: overrides.unit ?? "bag",
      purchasePrice: overrides.purchasePrice ?? 1000,
      sellingPrice: overrides.sellingPrice ?? 1200,
      stock: overrides.stock ?? 100,
      lowStockThreshold: overrides.lowStockThreshold ?? 10,
    })
    .returning();
  return p;
}

// ---- Small read helpers used in assertions -------------------------------

export async function getProduct(productId: string) {
  const [p] = await db.select().from(s.products).where(eq(s.products.id, productId));
  return p;
}

export async function getParty(partyId: string) {
  const [p] = await db.select().from(s.parties).where(eq(s.parties.id, partyId));
  return p;
}

export async function getSale(saleId: string) {
  const [row] = await db.select().from(s.sales).where(eq(s.sales.id, saleId));
  return row;
}

export async function getEventsByType(businessId: string, type: string) {
  return db
    .select()
    .from(s.events)
    .where(and(eq(s.events.businessId, businessId), eq(s.events.type, type)));
}

export async function getNotifications(businessId: string) {
  return db.select().from(s.notifications).where(eq(s.notifications.businessId, businessId));
}

export async function getExecutions(businessId: string) {
  return db.select().from(s.workflowExecutions).where(eq(s.workflowExecutions.businessId, businessId));
}
