import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";
import { setupTestDb } from "@/test/db";
import { makeBusiness, makeCustomer, makeProduct } from "@/test/factories";
import { createSale } from "./sales";
import { recordPayment } from "./payments";
import { loadOverview } from "@/lib/analytics";

beforeEach(setupTestDb);

test("a business cannot sell another business's product", async () => {
  const a = await makeBusiness({ name: "A" });
  const b = await makeBusiness({ name: "B" });
  const productOfB = await makeProduct(b.id, { stock: 100 });

  await assert.rejects(
    () => createSale(a.id, { items: [{ productId: productOfB.id, description: "Rice", quantity: 1, unitPrice: 10 }] }),
    /not available/,
  );
});

test("a business cannot attach another business's party to a sale", async () => {
  const a = await makeBusiness({ name: "A" });
  const b = await makeBusiness({ name: "B" });
  const productOfA = await makeProduct(a.id, { stock: 100 });
  const customerOfB = await makeCustomer(b.id, "B's customer");

  await assert.rejects(
    () =>
      createSale(a.id, {
        partyId: customerOfB.id,
        items: [{ productId: productOfA.id, description: "Rice", quantity: 1, unitPrice: 10 }],
      }),
    /was not found/,
  );
});

test("a business cannot record a payment against another business's invoice", async () => {
  const a = await makeBusiness({ name: "A" });
  const b = await makeBusiness({ name: "B" });
  const productOfA = await makeProduct(a.id, { stock: 100 });
  const sale = await createSale(a.id, {
    items: [{ productId: productOfA.id, description: "Rice", quantity: 1, unitPrice: 10 }],
    amountPaid: 0,
  });

  await assert.rejects(() => recordPayment(b.id, { saleId: sale.id, amount: 5 }), /Sale not found/);
});

test("analytics for one business never sees another's data", async () => {
  const a = await makeBusiness({ name: "A", taxRate: 0 });
  const b = await makeBusiness({ name: "B", taxRate: 0 });
  const pa = await makeProduct(a.id, { stock: 100, sellingPrice: 100 });
  const pb = await makeProduct(b.id, { stock: 100, sellingPrice: 100 });
  await createSale(a.id, { items: [{ productId: pa.id, description: "x", quantity: 1, unitPrice: 100 }] });
  await createSale(b.id, { items: [{ productId: pb.id, description: "x", quantity: 9, unitPrice: 100 }] });

  const oa = await loadOverview(a.id);
  assert.equal(oa.totals.sales, 100, "A only sees its own 100, not B's 900");
  assert.equal(oa.totals.salesCount, 1);
});
