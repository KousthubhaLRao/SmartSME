import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";
import { and, eq } from "drizzle-orm";
import { setupTestDb, db } from "@/test/db";
import { makeBusiness, makeSupplier, makeProduct, getProduct, getParty } from "@/test/factories";
import * as s from "@/db/schema";
import { createPurchase, cancelPurchase, updatePurchaseDate } from "./purchases";

beforeEach(setupTestDb);

test("createPurchase: adds stock, raises the payable, references the PO, and drains its events", async () => {
  const biz = await makeBusiness({ taxRate: 18 });
  const sup = await makeSupplier(biz.id);
  const prod = await makeProduct(biz.id, { stock: 10, purchasePrice: 1000 });

  const pur = await createPurchase(biz.id, {
    partyId: sup.id,
    items: [{ productId: prod.id, description: "Rice", quantity: 20, unitPrice: 1000 }],
    amountPaid: 0,
  });

  assert.equal(pur.subtotal, 20000);
  assert.equal(pur.total, 23600); // 20000 + 18%
  assert.equal(pur.referenceNumber, "PO-0001");
  assert.equal((await getProduct(prod.id)).stock, 30, "stock increased by qty");
  assert.equal((await getParty(sup.id)).balance, 23600, "full total is payable");

  const events = await db.select().from(s.events).where(eq(s.events.businessId, biz.id));
  assert.ok(events.length >= 2);
  assert.ok(events.every((e) => e.status === "done"));
});

test("cancelPurchase: removes the received stock and reverses the payable", async () => {
  const biz = await makeBusiness({ taxRate: 18 });
  const sup = await makeSupplier(biz.id);
  const prod = await makeProduct(biz.id, { stock: 10, purchasePrice: 1000 });
  const pur = await createPurchase(biz.id, {
    partyId: sup.id,
    items: [{ productId: prod.id, description: "Rice", quantity: 20, unitPrice: 1000 }],
    amountPaid: 0,
  });

  await cancelPurchase(biz.id, pur.id);

  assert.equal((await getProduct(prod.id)).stock, 10, "received stock removed");
  assert.equal((await getParty(sup.id)).balance, 0, "payable reversed");
  const [row] = await db.select().from(s.purchases).where(eq(s.purchases.id, pur.id));
  assert.equal(row.status, "cancelled");
});

test("updatePurchaseDate: back-dates a purchase", async () => {
  const biz = await makeBusiness();
  const prod = await makeProduct(biz.id, { stock: 0 });
  const pur = await createPurchase(biz.id, {
    items: [{ productId: prod.id, description: "x", quantity: 5, unitPrice: 10 }],
  });
  await updatePurchaseDate(biz.id, pur.id, new Date(2026, 0, 1));
  const [row] = await db.select().from(s.purchases).where(eq(s.purchases.id, pur.id));
  assert.equal(new Date(row.date).getFullYear(), 2026);
});
