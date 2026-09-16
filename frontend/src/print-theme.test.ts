/**
 * Invoices must print on white, and that is arranged purely in CSS.
 *
 * The dark palette lives inside `@media screen`, so the print stylesheet never
 * sees it and the light values on `:root` are what reaches the printer. It is
 * a structural property of one file, invisible at a glance, and easy to undo by
 * accident — someone tidies `index.css`, the `.dark` block drifts out of the
 * media query, and invoices silently start printing on a near-black background
 * that eats a toner cartridge and reads badly.
 *
 * The previous approach stripped the `.dark` class off `<html>` during printing
 * and restored it afterwards. It produced the right PDF and the wrong
 * experience: the live page visibly flashed to light and back around every
 * print. These tests exist so nobody reaches for that again.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const read = (relative: string) =>
  readFileSync(fileURLToPath(new URL(relative, import.meta.url)), "utf8");

/** The at-rules enclosing a position, outermost first. */
function enclosingAtRules(css: string, position: number): string[] {
  const stack: string[] = [];
  let depth = 0;
  for (let i = position; i > 0; i--) {
    const ch = css[i - 1];
    if (ch === "}") depth++;
    else if (ch === "{") {
      if (depth === 0) {
        const start = css.lastIndexOf("}", i - 2) + 1;
        stack.push(
          css
            .slice(start, i - 1)
            .trim()
            .split("\n")
            .pop()!
            .trim(),
        );
      } else depth--;
    }
  }
  return stack.reverse();
}

describe("invoices print on a light background", () => {
  const css = read("./index.css");

  it("keeps every .dark override inside @media screen", () => {
    const matches = [...css.matchAll(/(?<![\w-])\.dark\s*\{/g)];
    expect(matches.length).toBeGreaterThan(0);

    for (const match of matches) {
      const enclosing = enclosingAtRules(css, match.index!);
      expect(
        enclosing.some((rule) => rule.startsWith("@media") && rule.includes("screen")),
        `.dark block at index ${match.index} is not inside @media screen, so it would ` +
          `apply when printing and invoices would come out dark. Enclosed by: ` +
          `${JSON.stringify(enclosing)}`,
      ).toBe(true);
    }
  });

  it("keeps the light palette unconditional, so print inherits it", () => {
    const root = css.search(/(?<![\w-]):root\s*\{/);
    expect(root).toBeGreaterThan(-1);
    const enclosing = enclosingAtRules(css, root);
    expect(
      enclosing.filter((rule) => rule.startsWith("@media")),
      "the light :root palette must not sit inside a media query",
    ).toEqual([]);
  });

  it("does not swap the theme on the live page to do it", () => {
    // Comments stripped first: the file explains at length why it no longer
    // listens for beforeprint, and a test that reads prose rather than code
    // fails on its own documentation.
    const code = read("./components/PrintButton.tsx")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/\/\/.*$/gm, "");

    expect(code).not.toMatch(/classList/);
    expect(code).not.toMatch(/beforeprint|afterprint/);
    expect(code).toMatch(/window\.print\(\)/);
  });
});
