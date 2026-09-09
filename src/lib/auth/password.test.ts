import test from "node:test";
import assert from "node:assert/strict";
import { hashPassword, verifyPassword } from "./password";

test("hashPassword produces a pbkdf2 record that verifies", async () => {
  const stored = await hashPassword("correct horse battery staple");
  assert.match(stored, /^pbkdf2\$[0-9a-f]+\$[0-9a-f]+$/);
  assert.equal(await verifyPassword("correct horse battery staple", stored), true);
});

test("verifyPassword rejects the wrong password", async () => {
  const stored = await hashPassword("s3cret");
  assert.equal(await verifyPassword("s3cre7", stored), false);
  assert.equal(await verifyPassword("", stored), false);
});

test("verifyPassword rejects a malformed stored value", async () => {
  assert.equal(await verifyPassword("x", "garbage"), false);
  assert.equal(await verifyPassword("x", "bcrypt$salt$hash"), false);
  assert.equal(await verifyPassword("x", ""), false);
});

test("the same password hashes differently each time (random salt)", async () => {
  const a = await hashPassword("same");
  const b = await hashPassword("same");
  assert.notEqual(a, b);
  // ...but both still verify
  assert.equal(await verifyPassword("same", a), true);
  assert.equal(await verifyPassword("same", b), true);
});
