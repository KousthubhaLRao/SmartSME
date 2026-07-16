import test from "node:test";
import assert from "node:assert/strict";
import { calculateSaleTotals } from "./sales";

test("amount discounts reduce the subtotal before tax", () => {
  const totals = calculateSaleTotals(100, 10, "amount", 10);
  assert.equal(totals.discountAmount, 10);
  assert.equal(totals.tax, 9);
  assert.equal(totals.total, 99);
});

test("percentage discounts reduce the subtotal before tax", () => {
  const totals = calculateSaleTotals(100, 10, "percentage", 10);
  assert.equal(totals.discountAmount, 10);
  assert.equal(totals.tax, 9);
  assert.equal(totals.total, 99);
});
