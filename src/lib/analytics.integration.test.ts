import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";
import { setupTestDb } from "@/test/db";
import { makeBusiness, makeProduct } from "@/test/factories";
import { createSale } from "@/lib/domain/sales";
import { createPurchase } from "@/lib/domain/purchases";
import { createExpense } from "@/lib/domain/expenses";
import { loadOverview, getRevenueSeries } from "@/lib/analytics";

beforeEach(setupTestDb);

test("loadOverview aggregates totals, profit, inventory value and receivable", async () => {
  const biz = await makeBusiness({ taxRate: 0 });
  const prod = await makeProduct(biz.id, { stock: 100, purchasePrice: 100, sellingPrice: 150 });
  // One unpaid walk-in sale of 10 units at 150.
  await createSale(biz.id, {
    items: [{ productId: prod.id, description: "Rice", quantity: 10, unitPrice: 150 }],
    amountPaid: 0,
  });
  await createExpense(biz.id, { category: "Rent", description: "rent", amount: 200 });

  const o = await loadOverview(biz.id);

  assert.equal(o.totals.sales, 1500);
  assert.equal(o.totals.expenses, 200);
  assert.equal(o.totals.salesCount, 1);
  assert.equal(o.totals.receivable, 1500, "unpaid walk-in sale is receivable");
  assert.equal(o.totals.payable, 0);
  assert.equal(o.totals.inventoryValue, 9000, "90 units left at cost 100");
  assert.equal(o.totals.grossProfit, 500, "revenue 1500 minus COGS 1000");

  assert.equal(o.topProducts[0]?.label, "Rice");
  assert.equal(o.topProducts[0]?.value, 1500);
});

test("health scores stay within 0..100", async () => {
  const biz = await makeBusiness({ taxRate: 0 });
  const prod = await makeProduct(biz.id, { stock: 100, purchasePrice: 100, sellingPrice: 150 });
  await createSale(biz.id, { items: [{ productId: prod.id, description: "Rice", quantity: 5, unitPrice: 150 }] });
  await createPurchase(biz.id, { items: [{ productId: prod.id, description: "Rice", quantity: 5, unitPrice: 100 }] });
  await createExpense(biz.id, { category: "Rent", description: "rent", amount: 100 });

  const { health } = await loadOverview(biz.id);
  for (const key of ["overall", "inventory", "revenue", "expense", "cashFlow"] as const) {
    assert.ok(health[key] >= 0 && health[key] <= 100, `${key} within range (${health[key]})`);
  }
});

test("getRevenueSeries buckets today's sale into a 7-day window", async () => {
  const biz = await makeBusiness({ taxRate: 0 });
  const prod = await makeProduct(biz.id, { stock: 100, sellingPrice: 150 });
  await createSale(biz.id, { items: [{ productId: prod.id, description: "Rice", quantity: 2, unitPrice: 150 }] });

  const series = await getRevenueSeries(biz.id, 7);
  assert.equal(series.length, 7);
  assert.equal(series.reduce((a, b) => a + b.value, 0), 300, "the single sale lands in one bucket");
});
