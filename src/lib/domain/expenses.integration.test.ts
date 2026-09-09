import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";
import { eq } from "drizzle-orm";
import { setupTestDb, db } from "@/test/db";
import { makeBusiness, getNotifications, getEventsByType } from "@/test/factories";
import * as s from "@/db/schema";
import { createExpense, deleteExpense } from "./expenses";

beforeEach(setupTestDb);

test("createExpense records the expense and emits an EXPENSE_ADDED event", async () => {
  const biz = await makeBusiness();
  const e = await createExpense(biz.id, { category: "Rent", description: "Shop rent", amount: 18000 });
  assert.equal(e.category, "Rent");
  assert.equal(e.amount, 18000);
  const events = await getEventsByType(biz.id, "EXPENSE_ADDED");
  assert.equal(events.length, 1);
  assert.equal(events[0].status, "done");
});

test("the high-value rule flags a large expense and notifies", async () => {
  const biz = await makeBusiness({ withDefaultRules: true });
  const e = await createExpense(biz.id, { category: "Rent", description: "Shop rent", amount: 15000 });
  const [row] = await db.select().from(s.expenses).where(eq(s.expenses.id, e.id));
  assert.ok(row.flagged, "expense over the threshold is flagged");
  const notes = await getNotifications(biz.id);
  assert.ok(notes.some((n) => n.type === "workflow"), "a workflow notification was raised");
});

test("a small expense is not flagged", async () => {
  const biz = await makeBusiness({ withDefaultRules: true });
  const e = await createExpense(biz.id, { category: "Misc", description: "Tea", amount: 500 });
  const [row] = await db.select().from(s.expenses).where(eq(s.expenses.id, e.id));
  assert.equal(row.flagged, null);
});

test("createExpense validates amount and description; deleteExpense removes it", async () => {
  const biz = await makeBusiness();
  await assert.rejects(() => createExpense(biz.id, { category: "X", description: "x", amount: 0 }), /greater than zero/);
  await assert.rejects(() => createExpense(biz.id, { category: "X", description: "  ", amount: 10 }), /Description is required/);

  const e = await createExpense(biz.id, { category: "X", description: "keep", amount: 10 });
  await deleteExpense(biz.id, e.id);
  const rows = await db.select().from(s.expenses).where(eq(s.expenses.id, e.id));
  assert.equal(rows.length, 0);
});
