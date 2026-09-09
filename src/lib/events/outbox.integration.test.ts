import test, { beforeEach } from "node:test";
import assert from "node:assert/strict";
import { and, eq } from "drizzle-orm";
import { setupTestDb, db } from "@/test/db";
import { makeBusiness, makeProduct } from "@/test/factories";
import * as s from "@/db/schema";
import { publish } from "@/lib/events/publish";
import { drainQueue } from "@/worker/loop";
import { createSale } from "@/lib/domain/sales";

beforeEach(setupTestDb);

test("publish appends a pending event; drainQueue processes it to done", async () => {
  const biz = await makeBusiness();
  await publish(db, biz.id, "PING", { hello: "world" });

  let [ev] = await db.select().from(s.events).where(eq(s.events.businessId, biz.id));
  assert.equal(ev.status, "pending");
  assert.equal(ev.retryCount, 0);

  const processed = await drainQueue();
  assert.ok(processed >= 1);
  [ev] = await db.select().from(s.events).where(eq(s.events.businessId, biz.id));
  assert.equal(ev.status, "done");
  assert.ok(ev.processedAt, "processedAt is stamped");
});

test("a sale emits a chained STOCK_UPDATED, both processed", async () => {
  const biz = await makeBusiness({ withDefaultRules: true });
  const prod = await makeProduct(biz.id, { stock: 100 });
  await createSale(biz.id, { items: [{ productId: prod.id, description: "x", quantity: 1, unitPrice: 10 }] });

  const created = await db.select().from(s.events).where(and(eq(s.events.businessId, biz.id), eq(s.events.type, "SALE_CREATED")));
  const stock = await db.select().from(s.events).where(and(eq(s.events.businessId, biz.id), eq(s.events.type, "STOCK_UPDATED")));
  assert.equal(created.length, 1);
  assert.equal(stock.length, 1, "the sale chained a STOCK_UPDATED event");
  assert.ok([...created, ...stock].every((e) => e.status === "done"));
});

test("a permanently failing event dead-letters after the retry budget", async () => {
  const biz = await makeBusiness();
  // A SALE_CREATED pointing at a sale that does not exist makes the handler throw
  // every time, which is exactly what the retry/dead-letter path is for.
  await publish(db, biz.id, "SALE_CREATED", { saleId: crypto.randomUUID() });

  await drainQueue(); // loops internally until nothing is left to do

  const [ev] = await db.select().from(s.events).where(eq(s.events.businessId, biz.id));
  assert.equal(ev.status, "dead");
  assert.equal(ev.retryCount, 5);
  assert.match(ev.error ?? "", /Sale not found/);
});
