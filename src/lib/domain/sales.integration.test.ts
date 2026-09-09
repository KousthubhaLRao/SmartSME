import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";
import { and, eq } from "drizzle-orm";
import { setupTestDb, db } from "@/test/db";
import { makeBusiness, makeCustomer, makeProduct, getProduct, getParty, getSale } from "@/test/factories";
import * as s from "@/db/schema";
import { drainQueue } from "@/worker/loop";
import { createSale, cancelSale, updateSaleDate } from "./sales";

beforeEach(setupTestDb);

test("createSale: decrements stock, raises the receivable, numbers the invoice, and processes its events", async () => {
  const biz = await makeBusiness({ taxRate: 18, withDefaultRules: true });
  const cust = await makeCustomer(biz.id);
  const prod = await makeProduct(biz.id, { stock: 100, sellingPrice: 1200 });

  const sale = await createSale(biz.id, {
    partyId: cust.id,
    items: [{ productId: prod.id, description: "Rice", quantity: 10, unitPrice: 1200 }],
    amountPaid: 0,
  });

  assert.equal(sale.subtotal, 12000);
  assert.equal(sale.tax, 2160);
  assert.equal(sale.total, 14160);
  assert.equal(sale.paymentStatus, "unpaid");
  assert.equal(sale.invoiceNumber, "INV-0001");

  assert.equal((await getProduct(prod.id)).stock, 90, "stock reduced by qty");
  assert.equal((await getParty(cust.id)).balance, 14160, "full total is receivable");

  const items = await db.select().from(s.saleItems).where(eq(s.saleItems.saleId, sale.id));
  assert.equal(items.length, 1);
  assert.equal(items[0].lineTotal, 12000);

  const moves = await db
    .select()
    .from(s.stockMovements)
    .where(and(eq(s.stockMovements.refId, sale.id), eq(s.stockMovements.reason, "sale")));
  assert.equal(moves.length, 1);
  assert.equal(moves[0].delta, -10);

  const events = await db.select().from(s.events).where(eq(s.events.businessId, biz.id));
  assert.ok(events.length >= 2, "SALE_CREATED and a chained STOCK_UPDATED");
  assert.ok(events.every((e) => e.status === "done"), "every event drained to done");
});

test("createSale: second invoice increments the number", async () => {
  const biz = await makeBusiness();
  const p = await makeProduct(biz.id, { stock: 100 });
  const a = await createSale(biz.id, { items: [{ productId: p.id, description: "x", quantity: 1, unitPrice: 10 }] });
  const b = await createSale(biz.id, { items: [{ productId: p.id, description: "x", quantity: 1, unitPrice: 10 }] });
  assert.equal(a.invoiceNumber, "INV-0001");
  assert.equal(b.invoiceNumber, "INV-0002");
});

test("createSale: refuses to oversell and leaves stock untouched", async () => {
  const biz = await makeBusiness();
  const prod = await makeProduct(biz.id, { stock: 5 });
  await assert.rejects(
    () =>
      createSale(biz.id, {
        items: [{ productId: prod.id, description: "Rice", quantity: 10, unitPrice: 100 }],
      }),
    /Not enough stock/,
  );
  assert.equal((await getProduct(prod.id)).stock, 5, "stock unchanged after a rejected sale");
  const sales = await db.select().from(s.sales).where(eq(s.sales.businessId, biz.id));
  assert.equal(sales.length, 0, "no sale row was created");
});

test("createSale: rejects a discount larger than the sale and a negative discount", async () => {
  const biz = await makeBusiness({ taxRate: 0 });
  const prod = await makeProduct(biz.id, { stock: 100 });
  await assert.rejects(
    () =>
      createSale(biz.id, {
        items: [{ productId: prod.id, description: "x", quantity: 1, unitPrice: 1000 }],
        discountType: "amount",
        discountValue: 2000,
      }),
    /more than the sale value/,
  );
  await assert.rejects(
    () =>
      createSale(biz.id, {
        items: [{ productId: prod.id, description: "x", quantity: 1, unitPrice: 1000 }],
        discountType: "amount",
        discountValue: -5,
      }),
    /can't be negative/,
  );
});

test("createSale: clamps an overpayment to the total and marks it paid", async () => {
  const biz = await makeBusiness({ taxRate: 18 });
  const cust = await makeCustomer(biz.id);
  const prod = await makeProduct(biz.id, { stock: 100, sellingPrice: 1200 });
  const sale = await createSale(biz.id, {
    partyId: cust.id,
    items: [{ productId: prod.id, description: "Rice", quantity: 10, unitPrice: 1200 }],
    amountPaid: 999999,
  });
  assert.equal(sale.amountPaid, 14160, "amountPaid clamped to total");
  assert.equal(sale.paymentStatus, "paid");
  assert.equal((await getParty(cust.id)).balance, 0, "nothing outstanding");
});

test("cancelSale: restores stock, reverses the receivable, and marks it cancelled", async () => {
  const biz = await makeBusiness({ taxRate: 18 });
  const cust = await makeCustomer(biz.id);
  const prod = await makeProduct(biz.id, { stock: 100, sellingPrice: 1200 });
  const sale = await createSale(biz.id, {
    partyId: cust.id,
    items: [{ productId: prod.id, description: "Rice", quantity: 10, unitPrice: 1200 }],
    amountPaid: 0,
  });

  await cancelSale(biz.id, sale.id);

  assert.equal((await getProduct(prod.id)).stock, 100, "stock restored");
  assert.equal((await getParty(cust.id)).balance, 0, "receivable reversed");
  assert.equal((await getSale(sale.id)).status, "cancelled");
});

test("createSale event is replay-safe: re-draining does not double-apply", async () => {
  const biz = await makeBusiness({ taxRate: 18, withDefaultRules: true });
  const cust = await makeCustomer(biz.id);
  const prod = await makeProduct(biz.id, { stock: 100, sellingPrice: 1200 });
  const sale = await createSale(biz.id, {
    partyId: cust.id,
    items: [{ productId: prod.id, description: "Rice", quantity: 10, unitPrice: 1200 }],
    amountPaid: 0,
  });
  assert.equal((await getProduct(prod.id)).stock, 90);

  // Force a replay of the already-processed SALE_CREATED event.
  await db
    .update(s.events)
    .set({ status: "pending" })
    .where(and(eq(s.events.businessId, biz.id), eq(s.events.type, "SALE_CREATED")));
  await drainQueue();

  assert.equal((await getProduct(prod.id)).stock, 90, "stock not decremented twice");
  assert.equal((await getParty(cust.id)).balance, 14160, "receivable not added twice");
  const moves = await db
    .select()
    .from(s.stockMovements)
    .where(and(eq(s.stockMovements.refId, sale.id), eq(s.stockMovements.reason, "sale")));
  assert.equal(moves.length, 1, "still exactly one sale stock movement");
});

test("updateSaleDate: back-dates a sale and rejects an invalid date", async () => {
  const biz = await makeBusiness();
  const prod = await makeProduct(biz.id, { stock: 100 });
  const sale = await createSale(biz.id, {
    items: [{ productId: prod.id, description: "x", quantity: 1, unitPrice: 10 }],
  });
  const backdated = new Date(2026, 0, 1);
  await updateSaleDate(biz.id, sale.id, backdated);
  assert.equal(new Date((await getSale(sale.id)).date).getFullYear(), 2026);
  await assert.rejects(() => updateSaleDate(biz.id, sale.id, new Date("nonsense")), /isn't valid/);
});
