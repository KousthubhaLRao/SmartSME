import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";
import { and, eq } from "drizzle-orm";
import { setupTestDb, db } from "@/test/db";
import { makeBusiness, getParty } from "@/test/factories";
import * as s from "@/db/schema";
import { createParty, updateParty, deleteParty } from "./parties";

beforeEach(setupTestDb);

test("createParty creates a customer with an opening balance", async () => {
  const biz = await makeBusiness();
  const p = await createParty(biz.id, { type: "customer", name: "Kumar Traders", openingBalance: 500 });
  assert.equal(p.type, "customer");
  assert.equal(p.name, "Kumar Traders");
  assert.equal(p.balance, 500);
});

test("createParty creates a supplier and defaults its type safely", async () => {
  const biz = await makeBusiness();
  const p = await createParty(biz.id, { type: "supplier", name: "ABC Suppliers" });
  assert.equal(p.type, "supplier");
  assert.equal(p.balance, 0);
});

test("createParty normalizes phone numbers and rejects invalid ones", async () => {
  const biz = await makeBusiness();
  const p = await createParty(biz.id, { type: "customer", name: "Anita", phone: "+91 90000-11111" });
  assert.equal(p.phone, "+919000011111");
  await assert.rejects(
    () => createParty(biz.id, { type: "customer", name: "Bad", phone: "call-me" }),
    /digits and an optional leading/,
  );
});

test("createParty requires a name", async () => {
  const biz = await makeBusiness();
  await assert.rejects(() => createParty(biz.id, { type: "customer", name: "   " }), /Name is required/);
});

test("updateParty edits fields, deleteParty removes the row", async () => {
  const biz = await makeBusiness();
  const p = await createParty(biz.id, { type: "customer", name: "Old Name" });
  await updateParty(biz.id, p.id, { type: "customer", name: "New Name", email: "n@x.com" });
  const after = await getParty(p.id);
  assert.equal(after.name, "New Name");
  assert.equal(after.email, "n@x.com");

  await deleteParty(biz.id, p.id);
  const [gone] = await db
    .select()
    .from(s.parties)
    .where(and(eq(s.parties.id, p.id), eq(s.parties.businessId, biz.id)));
  assert.equal(gone, undefined);
});
