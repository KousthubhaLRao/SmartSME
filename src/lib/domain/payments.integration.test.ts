import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";
import { eq } from "drizzle-orm";
import { setupTestDb, db } from "@/test/db";
import { makeBusiness, makeCustomer, makeSupplier, makeProduct, getParty, getSale } from "@/test/factories";
import * as s from "@/db/schema";
import { createSale, cancelSale } from "./sales";
import { createPurchase } from "./purchases";
import { recordPayment, settleParty, settleAllOutstanding } from "./payments";

beforeEach(setupTestDb);

async function unpaidSale(bizId: string, custId: string, productId: string) {
  return createSale(bizId, {
    partyId: custId,
    items: [{ productId, description: "Rice", quantity: 10, unitPrice: 1200 }],
    amountPaid: 0,
  });
}

test("recordPayment on a sale: partial then full, snapping the balance to zero", async () => {
  const biz = await makeBusiness({ taxRate: 18 });
  const cust = await makeCustomer(biz.id);
  const prod = await makeProduct(biz.id, { stock: 100, sellingPrice: 1200 });
  const sale = await unpaidSale(biz.id, cust.id, prod.id); // total 14160

  await recordPayment(biz.id, { saleId: sale.id, amount: 4160 });
  let row = await getSale(sale.id);
  assert.equal(row.amountPaid, 4160);
  assert.equal(row.paymentStatus, "partial");
  assert.equal((await getParty(cust.id)).balance, 10000);

  await recordPayment(biz.id, { saleId: sale.id, amount: 10000 });
  row = await getSale(sale.id);
  assert.equal(row.amountPaid, 14160);
  assert.equal(row.paymentStatus, "paid");
  assert.equal((await getParty(cust.id)).balance, 0);
});

test("recordPayment: an overpayment never drives the balance negative", async () => {
  const biz = await makeBusiness({ taxRate: 18 });
  const cust = await makeCustomer(biz.id);
  const prod = await makeProduct(biz.id, { stock: 100, sellingPrice: 1200 });
  const sale = await unpaidSale(biz.id, cust.id, prod.id);
  await recordPayment(biz.id, { saleId: sale.id, amount: 999999 });
  assert.equal((await getSale(sale.id)).amountPaid, 14160);
  assert.equal((await getParty(cust.id)).balance, 0);
});

test("recordPayment: rejects non-positive amounts and cancelled sales", async () => {
  const biz = await makeBusiness();
  const cust = await makeCustomer(biz.id);
  const prod = await makeProduct(biz.id, { stock: 100, sellingPrice: 1200 });
  const sale = await unpaidSale(biz.id, cust.id, prod.id);

  await assert.rejects(() => recordPayment(biz.id, { saleId: sale.id, amount: 0 }), /greater than zero/);
  await cancelSale(biz.id, sale.id);
  await assert.rejects(() => recordPayment(biz.id, { saleId: sale.id, amount: 100 }), /cancelled/);
});

test("recordPayment on a purchase reduces the payable", async () => {
  const biz = await makeBusiness({ taxRate: 0 });
  const sup = await makeSupplier(biz.id);
  const prod = await makeProduct(biz.id, { stock: 0, purchasePrice: 100 });
  const pur = await createPurchase(biz.id, {
    partyId: sup.id,
    items: [{ productId: prod.id, description: "Rice", quantity: 10, unitPrice: 100 }],
    amountPaid: 0,
  }); // total 1000
  await recordPayment(biz.id, { purchaseId: pur.id, amount: 400 });
  const [row] = await db.select().from(s.purchases).where(eq(s.purchases.id, pur.id));
  assert.equal(row.amountPaid, 400);
  assert.equal(row.paymentStatus, "partial");
  assert.equal((await getParty(sup.id)).balance, 600);
});

test("settleParty clears every open invoice and the running balance", async () => {
  const biz = await makeBusiness({ taxRate: 0 });
  const cust = await makeCustomer(biz.id);
  const prod = await makeProduct(biz.id, { stock: 100, sellingPrice: 100 });
  await createSale(biz.id, { partyId: cust.id, items: [{ productId: prod.id, description: "x", quantity: 2, unitPrice: 100 }], amountPaid: 0 });
  await createSale(biz.id, { partyId: cust.id, items: [{ productId: prod.id, description: "x", quantity: 3, unitPrice: 100 }], amountPaid: 0 });

  const result = await settleParty(biz.id, cust.id);
  assert.equal(result.count, 2);
  assert.equal(result.total, 500);
  assert.equal((await getParty(cust.id)).balance, 0);
  const sales = await db.select().from(s.sales).where(eq(s.sales.businessId, biz.id));
  assert.ok(sales.every((x) => x.paymentStatus === "paid"));
});

test("settleAllOutstanding marks every receivable paid and clears customer balances", async () => {
  const biz = await makeBusiness({ taxRate: 0 });
  const a = await makeCustomer(biz.id, "A");
  const b = await makeCustomer(biz.id, "B");
  const prod = await makeProduct(biz.id, { stock: 100, sellingPrice: 100 });
  await createSale(biz.id, { partyId: a.id, items: [{ productId: prod.id, description: "x", quantity: 1, unitPrice: 100 }], amountPaid: 0 });
  await createSale(biz.id, { partyId: b.id, items: [{ productId: prod.id, description: "x", quantity: 2, unitPrice: 100 }], amountPaid: 0 });

  const result = await settleAllOutstanding(biz.id, "receivable");
  assert.equal(result.count, 2);
  assert.equal(result.total, 300);
  assert.equal((await getParty(a.id)).balance, 0);
  assert.equal((await getParty(b.id)).balance, 0);
});
