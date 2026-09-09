import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";
import { and, eq } from "drizzle-orm";
import { setupTestDb, db } from "@/test/db";
import { makeBusiness, makeProduct, getProduct, getNotifications } from "@/test/factories";
import * as s from "@/db/schema";
import { createSale } from "./sales";
import { createProduct, updateProduct, adjustStock, deleteProduct } from "./products";

beforeEach(setupTestDb);

test("createProduct records opening stock as a stock movement", async () => {
  const biz = await makeBusiness();
  const p = await createProduct(biz.id, { name: "Sugar", stock: 50, purchasePrice: 40, sellingPrice: 52 });
  assert.equal(p.stock, 50);
  const moves = await db.select().from(s.stockMovements).where(eq(s.stockMovements.productId, p.id));
  assert.equal(moves.length, 1);
  assert.equal(moves[0].delta, 50);
  assert.equal(moves[0].note, "Opening stock");
});

test("createProduct with no opening stock records no movement", async () => {
  const biz = await makeBusiness();
  const p = await createProduct(biz.id, { name: "Sugar", stock: 0 });
  const moves = await db.select().from(s.stockMovements).where(eq(s.stockMovements.productId, p.id));
  assert.equal(moves.length, 0);
});

test("createProduct validates name, prices, and stock", async () => {
  const biz = await makeBusiness();
  await assert.rejects(() => createProduct(biz.id, { name: "   " }), /name is required/i);
  await assert.rejects(() => createProduct(biz.id, { name: "X", purchasePrice: -1 }), /zero or more/);
  await assert.rejects(() => createProduct(biz.id, { name: "X", stock: -5 }), /zero or more/);
});

test("updateProduct changes details but not stock", async () => {
  const biz = await makeBusiness();
  const p = await makeProduct(biz.id, { name: "Old", stock: 30, sellingPrice: 100 });
  await updateProduct(biz.id, p.id, { name: "New", sellingPrice: 150, lowStockThreshold: 5 });
  const after = await getProduct(p.id);
  assert.equal(after.name, "New");
  assert.equal(after.sellingPrice, 150);
  assert.equal(after.lowStockThreshold, 5);
  assert.equal(after.stock, 30, "updateProduct must not touch stock");
});

test("adjustStock moves stock, logs a movement, and emits a low-stock alert", async () => {
  const biz = await makeBusiness({ withDefaultRules: true });
  const p = await makeProduct(biz.id, { stock: 100, lowStockThreshold: 10 });
  await adjustStock(biz.id, p.id, -95, "Damaged");
  assert.equal((await getProduct(p.id)).stock, 5);
  const moves = await db.select().from(s.stockMovements).where(eq(s.stockMovements.productId, p.id));
  assert.ok(moves.some((m) => m.delta === -95 && m.reason === "adjustment"));
  const notes = await getNotifications(biz.id);
  assert.ok(notes.some((n) => n.type === "low_stock"), "low-stock alert raised");
});

test("adjustStock refuses to go below zero or by nothing", async () => {
  const biz = await makeBusiness();
  const p = await makeProduct(biz.id, { stock: 5 });
  await assert.rejects(() => adjustStock(biz.id, p.id, -10, "x"), /Only 5/);
  await assert.rejects(() => adjustStock(biz.id, p.id, 0, "x"), /non-zero/);
});

test("deleteProduct is blocked once the product is on an invoice", async () => {
  const biz = await makeBusiness();
  const used = await makeProduct(biz.id, { stock: 100 });
  await createSale(biz.id, { items: [{ productId: used.id, description: "Rice", quantity: 1, unitPrice: 10 }] });
  await assert.rejects(() => deleteProduct(biz.id, used.id), /past invoices/);

  const unused = await makeProduct(biz.id, { name: "Never sold", stock: 0 });
  await deleteProduct(biz.id, unused.id);
  const [gone] = await db
    .select()
    .from(s.products)
    .where(and(eq(s.products.id, unused.id), eq(s.products.businessId, biz.id)));
  assert.equal(gone, undefined, "unused product removed");
});
