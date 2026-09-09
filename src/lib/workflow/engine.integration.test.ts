import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";
import { setupTestDb, db } from "@/test/db";
import { makeBusiness, makeProduct, getNotifications, getExecutions } from "@/test/factories";
import * as s from "@/db/schema";
import { createExpense } from "@/lib/domain/expenses";
import { createSale } from "@/lib/domain/sales";
import { adjustStock } from "@/lib/domain/products";

beforeEach(setupTestDb);

async function addRule(businessId: string, rule: Partial<typeof s.workflowRules.$inferInsert>) {
  await db.insert(s.workflowRules).values({
    businessId,
    name: rule.name ?? "rule",
    eventType: rule.eventType ?? "EXPENSE_ADDED",
    actionType: rule.actionType ?? "notify",
    ...rule,
  } as typeof s.workflowRules.$inferInsert);
}

test("numeric condition operators (lt) match and skip correctly", async () => {
  const biz = await makeBusiness();
  await addRule(biz.id, {
    name: "small-expense",
    eventType: "EXPENSE_ADDED",
    conditionField: "amount",
    conditionOp: "lt",
    conditionValue: "1000",
    actionType: "notify",
    actionConfig: { title: "Small expense" },
  });

  await createExpense(biz.id, { category: "Misc", description: "cheap", amount: 500 });
  await createExpense(biz.id, { category: "Misc", description: "dear", amount: 5000 });

  const execs = (await getExecutions(biz.id)).filter((e) => e.ruleName === "small-expense");
  assert.equal(execs.filter((e) => e.status === "matched").length, 1);
  assert.equal(execs.filter((e) => e.status === "skipped").length, 1);
});

test("string condition operators (neq) compare by value", async () => {
  const biz = await makeBusiness();
  await addRule(biz.id, {
    name: "non-rent",
    eventType: "EXPENSE_ADDED",
    conditionField: "category",
    conditionOp: "neq",
    conditionValue: "Rent",
    actionType: "notify",
    actionConfig: { title: "Non-rent expense" },
  });

  await createExpense(biz.id, { category: "Fuel", description: "diesel", amount: 100 });
  await createExpense(biz.id, { category: "Rent", description: "rent", amount: 100 });

  const execs = (await getExecutions(biz.id)).filter((e) => e.ruleName === "non-rent");
  assert.equal(execs.filter((e) => e.status === "matched").length, 1);
  assert.equal(execs.filter((e) => e.status === "skipped").length, 1);
});

test("a disabled rule never runs", async () => {
  const biz = await makeBusiness();
  await addRule(biz.id, {
    name: "off-rule",
    eventType: "EXPENSE_ADDED",
    actionType: "notify",
    enabled: false,
  });
  await createExpense(biz.id, { category: "X", description: "x", amount: 10 });
  const execs = await getExecutions(biz.id);
  assert.equal(execs.length, 0, "disabled rule produced no execution");
});

test("restock alert stays quiet when stock is healthy", async () => {
  const biz = await makeBusiness({ withDefaultRules: true });
  const p = await makeProduct(biz.id, { stock: 100, lowStockThreshold: 10 });
  await adjustStock(biz.id, p.id, -5, "sold a few"); // 95, still healthy
  const notes = await getNotifications(biz.id);
  assert.equal(notes.filter((n) => n.type === "low_stock").length, 0);
});

test("restock alert fires an out-of-stock error when stock hits zero", async () => {
  const biz = await makeBusiness({ withDefaultRules: true });
  const p = await makeProduct(biz.id, { stock: 5, lowStockThreshold: 10 });
  await adjustStock(biz.id, p.id, -5, "cleared"); // 0
  const notes = await getNotifications(biz.id);
  const out = notes.find((n) => n.type === "low_stock" && n.severity === "error");
  assert.ok(out, "an out-of-stock error notification was raised");
});

test("notifications with the same title dedupe while unread", async () => {
  const biz = await makeBusiness({ withDefaultRules: true });
  const prod = await makeProduct(biz.id, { stock: 100, sellingPrice: 100 });
  // Two unpaid walk-in sales both trigger the "Payment pending" reminder.
  await createSale(biz.id, { items: [{ productId: prod.id, description: "x", quantity: 1, unitPrice: 100 }], amountPaid: 0 });
  await createSale(biz.id, { items: [{ productId: prod.id, description: "x", quantity: 1, unitPrice: 100 }], amountPaid: 0 });
  const pending = (await getNotifications(biz.id)).filter((n) => n.title === "Payment pending" && !n.read);
  assert.equal(pending.length, 1, "the second identical unread alert was deduped");
});
