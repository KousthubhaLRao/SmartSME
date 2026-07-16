import test from "node:test";
import assert from "node:assert/strict";
import { calculateOutstandingTotal } from "./analytics";

test("calculateOutstandingTotal includes both party and walk-in invoices", () => {
  const rows = [
    { total: 100, amountPaid: 40 },
    { total: 80, amountPaid: 0 },
    { total: 50, amountPaid: 50 },
  ];

  assert.equal(calculateOutstandingTotal(rows), 140);
});
