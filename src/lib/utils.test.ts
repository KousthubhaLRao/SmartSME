import test from "node:test";
import assert from "node:assert/strict";
import {
  cn,
  round2,
  money,
  compactMoney,
  initials,
  errMsg,
  parseDateInput,
  toDateInputValue,
} from "./utils";

test("round2 rounds to two decimals", () => {
  assert.equal(round2(1.005), 1.01);
  assert.equal(round2(1.239), 1.24);
  assert.equal(round2(12000 * 0.18), 2160);
  assert.equal(round2(2), 2);
});

test("money formats with the right symbol and two decimals", () => {
  assert.equal(money(1234.5, "INR"), "₹1,234.50");
  assert.equal(money(1000, "USD"), "$1,000.00");
  assert.equal(money(0), "₹0.00");
  assert.equal(money(50, "ZZZ"), "50.00"); // unknown currency -> no symbol
});

test("compactMoney uses Indian K/L/Cr suffixes", () => {
  assert.equal(compactMoney(500), "₹500");
  assert.equal(compactMoney(1500), "₹1.5K");
  assert.equal(compactMoney(150000), "₹1.50L");
  assert.equal(compactMoney(20000000), "₹2.00Cr");
});

test("initials takes up to two leading letters", () => {
  assert.equal(initials("Kumar Traders"), "KT");
  assert.equal(initials("anita"), "A");
  assert.equal(initials("a b c"), "AB");
});

test("cn joins truthy class names only", () => {
  assert.equal(cn("a", false, "b", null, undefined, "c"), "a b c");
  assert.equal(cn(), "");
});

test("errMsg unwraps Error, falls back otherwise", () => {
  assert.equal(errMsg(new Error("boom")), "boom");
  assert.equal(errMsg("nope"), "Something went wrong.");
});

test("parseDateInput handles yyyy-mm-dd, ISO, and junk", () => {
  const d = parseDateInput("2026-01-15");
  assert.ok(d instanceof Date);
  assert.equal(d!.getFullYear(), 2026);
  assert.equal(d!.getMonth(), 0);
  assert.equal(d!.getDate(), 15);
  assert.equal(parseDateInput(""), undefined);
  assert.equal(parseDateInput("   "), undefined);
  assert.equal(parseDateInput("not-a-date"), undefined);
});

test("toDateInputValue formats a Date as yyyy-mm-dd", () => {
  assert.equal(toDateInputValue(new Date(2026, 0, 5)), "2026-01-05");
  assert.equal(toDateInputValue(new Date(2026, 11, 31)), "2026-12-31");
});
