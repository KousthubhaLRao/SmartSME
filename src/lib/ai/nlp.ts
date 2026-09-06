import { extractJson, getProvider } from "./client";

export interface ParsedCommand {
  eventType: "SALE_CREATED" | "PURCHASE_CREATED" | "ORDER_CREATED" | "EXPENSE_ADDED";
  party: string | null;
  product: string | null;
  quantity: number | null;
  amount: number | null;
  category: string | null;
  /** True when the note refers to the whole inventory ("sell the entire stock"). */
  allInventory: boolean;
  /** A discount attached to a sale: a percentage, a flat amount, or none. */
  discountType: "none" | "amount" | "percentage";
  /** The percent (for "percentage") or the flat currency figure (for "amount"). */
  discountValue: number;
  /** Transaction date as YYYY-MM-DD when the note states one, else null. */
  date: string | null;
  /** The provider label that parsed it (e.g. "Anthropic Claude"), or "Heuristic". */
  engine: string;
}

const SYSTEM =
  "You extract a single structured business event from an SME shopkeeper's plain-language note. Reply with JSON only, no prose or markdown.";

const PROMPT = (text: string, todayIso: string) =>
  `Extract one business event from the note and return ONLY a single minified JSON object with exactly these keys:
- eventType: one of "SALE_CREATED" (sold/sale), "PURCHASE_CREATED" (bought/purchased from a supplier), "ORDER_CREATED" (a customer wants/needs something later), "EXPENSE_ADDED" (rent, salary, utilities, fuel, etc.).
- party: the customer or supplier name, or null.
- product: the product name (singular, no unit words like "bags"/"packets"), or null.
- quantity: numeric quantity, or null.
- amount: total money value in rupees if stated, else null.
- category: expense category (e.g. Rent, Utilities) for EXPENSE_ADDED, else null.
- allInventory: true if the note refers to the ENTIRE inventory / all stock / everything in stock (e.g. "sell the entire inventory", "clear out all stock", "sell everything"); otherwise false. When true, leave product and quantity as null.
- discountType: "percentage" if a percentage discount is mentioned (e.g. "10% off", "discount of 10%"), "amount" if a flat money discount is mentioned (e.g. "discount of 300 rupees", "₹300 off"), otherwise "none".
- date: the date the transaction happened, as "YYYY-MM-DD", if the note states one (e.g. "on 20th August 2026", "yesterday", "3 Sept"); otherwise null. Today is ${todayIso} - resolve relative words like "today"/"yesterday" against it, and assume a bare day+month is the most recent past occurrence.
- discountValue: the numeric discount — the percent number for "percentage", or the rupee figure for "amount"; 0 when discountType is "none".
Use null where a value is unknown. No extra keys, no commentary.

Note: "${text}"`;

export async function parseCommand(text: string): Promise<ParsedCommand> {
  const provider = getProvider();
  if (provider) {
    try {
      const raw = await provider.complete({ system: SYSTEM, prompt: PROMPT(text, isoDate(new Date())), maxTokens: 1024 });
      const parsed = extractJson<Omit<ParsedCommand, "engine">>(raw);
      if (parsed && parsed.eventType) {
        return { ...normalize(parsed), engine: provider.label };
      }
    } catch (err) {
      console.warn("[nlp] provider parse failed, falling back to heuristic:", err);
    }
  }
  return { ...heuristicParse(text), engine: "Heuristic" };
}

function normalize(p: Partial<ParsedCommand>): Omit<ParsedCommand, "engine"> {
  return {
    eventType: (p.eventType as ParsedCommand["eventType"]) ?? "SALE_CREATED",
    party: p.party ?? null,
    product: p.product ?? null,
    quantity: p.quantity != null ? Number(p.quantity) : null,
    amount: p.amount != null ? Number(p.amount) : null,
    category: p.category ?? null,
    allInventory: Boolean(p.allInventory),
    discountType:
      p.discountType === "amount" || p.discountType === "percentage" ? p.discountType : "none",
    discountValue: p.discountValue != null && Number(p.discountValue) > 0 ? Number(p.discountValue) : 0,
    date: typeof p.date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(p.date) ? p.date : null,
  };
}

const MONTH_INDEX: Record<string, number> = {
  jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5,
  jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11,
};

function isoDate(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function shift(base: Date, days: number): Date {
  return new Date(base.getFullYear(), base.getMonth(), base.getDate() + days);
}

/** Picks the year for a bare day+month: the most recent one that is not future. */
function inferYear(month: number, day: number, today: Date): number {
  const y = today.getFullYear();
  return new Date(y, month, day) > today ? y - 1 : y;
}

function build(y: number, m: number, d: number): string | null {
  const dt = new Date(y, m, d);
  // Rejects impossible dates like 31 Feb, which JS would silently roll over.
  return dt.getMonth() === m && dt.getDate() === d ? isoDate(dt) : null;
}

/**
 * Pulls a transaction date out of a note ("on 20th August 2026", "yesterday",
 * "20/08/2026"). Returns YYYY-MM-DD, or null when the note states no date.
 */
export function parseDatePhrase(text: string, now = new Date()): string | null {
  const lower = text.toLowerCase();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());

  if (/\bday before yesterday\b/.test(lower)) return isoDate(shift(today, -2));
  if (/\byesterday\b/.test(lower)) return isoDate(shift(today, -1));
  if (/\btomorrow\b/.test(lower)) return isoDate(shift(today, 1));
  if (/\btoday\b/.test(lower)) return isoDate(today);

  // 2026-08-20
  let m = lower.match(/\b(\d{4})-(\d{2})-(\d{2})\b/);
  if (m) return build(Number(m[1]), Number(m[2]) - 1, Number(m[3]));

  // 20/08/2026 or 20-08-26 (day first, the Indian convention)
  m = lower.match(/\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b/);
  if (m) {
    const yr = Number(m[3]);
    return build(yr < 100 ? 2000 + yr : yr, Number(m[2]) - 1, Number(m[1]));
  }

  // "20th August 2026", "3 sept", "on 20 aug"
  m = lower.match(
    /\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?(?:,?\s*(\d{4}))?\b/,
  );
  if (m) {
    const day = Number(m[1]);
    const mon = MONTH_INDEX[m[2]];
    return build(m[3] ? Number(m[3]) : inferYear(mon, day, today), mon, day);
  }

  // "August 20 2026" / "on aug 20" — needs "on" or a year, so a stray "may 10
  // bags" is not read as a date.
  m = lower.match(
    /\b(on\s+)?(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(\d{4}))?\b/,
  );
  if (m && (m[1] || m[4])) {
    const mon = MONTH_INDEX[m[2]];
    const day = Number(m[3]);
    return build(m[4] ? Number(m[4]) : inferYear(mon, day, today), mon, day);
  }

  return null;
}

/** Pulls a "discount of 10%" / "discount of 300 rupees" clause out of a note. */
function parseDiscount(lower: string): { discountType: "none" | "amount" | "percentage"; discountValue: number } {
  // Note: no trailing \b after the alternation — "%" is a non-word char, so a
  // word boundary can never follow it and "10%" would fail to match.
  const pct =
    lower.match(/(?:discount|off)\D{0,15}?(\d[\d.]*)\s*(?:%|percent|pct)/) ??
    lower.match(/(\d[\d.]*)\s*(?:%|percent|pct)\s*(?:discount|off)?/);
  if (pct) return { discountType: "percentage", discountValue: Number(pct[1]) };

  const amt =
    lower.match(/discount\s+of\s+(?:₹|rs\.?|inr)?\s*(\d[\d,]*(?:\.\d+)?)/) ??
    lower.match(/(?:₹|rs\.?|inr)\s*(\d[\d,]*(?:\.\d+)?)\s*(?:discount|off)/);
  if (amt) return { discountType: "amount", discountValue: Number(amt[1].replace(/,/g, "")) };

  return { discountType: "none", discountValue: 0 };
}

const UNIT_WORDS =
  /\b(bags?|packets?|pkts?|boxes?|box|pcs?|pieces?|units?|kgs?|kg|kilograms?|grams?|g|litres?|liters?|ltrs?|l|dozens?|cartons?|of|the)\b/gi;

// A dependency-free parser for the common shapes. Good enough as a starting
// point; the confirmation screen lets the user correct anything before publish.
export function heuristicParse(text: string): Omit<ParsedCommand, "engine"> {
  const lower = text.toLowerCase();

  const allInventory =
    /\b(entire|all|whole|complete|full)\s+(inventory|stock|stocks|goods|products?)\b/.test(lower) ||
    /\b(sell|clear|sold|liquidat\w*)\s+everything\b/.test(lower);

  const { discountType, discountValue } = parseDiscount(lower);
  const date = parseDatePhrase(text);

  let eventType: ParsedCommand["eventType"] = "SALE_CREATED";
  if (/\b(bought|buy|purchase[ds]?|received|restock(?:ed)?)\b/.test(lower) && /\bfrom\b/.test(lower)) {
    eventType = "PURCHASE_CREATED";
  } else if (/\b(bought|buy|purchase[ds]?)\b/.test(lower)) {
    eventType = "PURCHASE_CREATED";
  } else if (/\b(order(?:ed)?|wants?|need[s]?|requires?|requested)\b/.test(lower)) {
    eventType = "ORDER_CREATED";
  } else if (
    // Strong expense words classify as an expense even with "to <payee>".
    /\b(rent|salary|wages?|electricity|utilit\w*|fuel|maintenance|internet)\b/.test(lower) ||
    /\b(expense|spent|spend|bill)\b/.test(lower) ||
    (/\bpaid\b/.test(lower) && !/\bto\b/.test(lower))
  ) {
    eventType = "EXPENSE_ADDED";
  } else if (/\b(sold|sell|sale)\b/.test(lower)) {
    eventType = "SALE_CREATED";
  }

  const qtyMatch = text.match(/\b(\d[\d,]*(?:\.\d+)?)\b/);
  const firstNumber = qtyMatch ? Number(qtyMatch[1].replace(/,/g, "")) : null;

  // Note: "at" is intentionally excluded, it usually marks a unit price
  // ("5 bags at 100 each"), not the total.
  const amtMatch = text.match(/(?:₹|rs\.?|inr|worth|for|amount)\s*(\d[\d,]*(?:\.\d+)?)/i);
  let amount = amtMatch ? Number(amtMatch[1].replace(/,/g, "")) : null;

  const partyMatch = text.match(
    /\b(?:to|from)\s+([A-Za-z0-9&.'\s]+?)(?:\s+(?:for|at|on|worth|tomorrow|today|₹|rs\b)|[.,!?]|$)/i,
  );
  const party = partyMatch ? titleCase(partyMatch[1].trim()) : null;

  if (eventType === "EXPENSE_ADDED") {
    amount = amount ?? firstNumber;
    const catMatch =
      text.match(/\bfor\s+([A-Za-z\s]+)/i) ??
      text.match(/\b(rent|salary|electricity|utilities?|fuel|transport|internet|maintenance|misc\w*)\b/i);
    const category = catMatch ? titleCase(catMatch[1].trim()) : "General";
    return {
      eventType,
      party: null,
      product: null,
      quantity: null,
      amount,
      category,
      allInventory: false,
      discountType: "none",
      discountValue: 0,
      date,
    };
  }

  // Product = words between the quantity and "to/from", with unit words stripped.
  let product: string | null = null;
  const midMatch = text.match(/\b\d[\d,]*(?:\.\d+)?\s+(.*?)(?:\s+(?:to|from|for|at|worth)\b|[.,!?]|$)/i);
  if (midMatch) {
    product = midMatch[1].replace(UNIT_WORDS, " ").replace(/\s+/g, " ").trim();
    if (!product) product = null;
  }

  return {
    eventType,
    party,
    product: product ? titleCase(product) : null,
    quantity: firstNumber,
    amount,
    category: null,
    allInventory,
    discountType,
    discountValue,
    date,
  };
}

function titleCase(s: string): string {
  return s
    .toLowerCase()
    .split(/\s+/)
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ")
    .trim();
}
