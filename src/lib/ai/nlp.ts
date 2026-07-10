import { extractJson, getProvider } from "./client";

export interface ParsedCommand {
  eventType: "SALE_CREATED" | "PURCHASE_CREATED" | "ORDER_CREATED" | "EXPENSE_ADDED";
  party: string | null;
  product: string | null;
  quantity: number | null;
  amount: number | null;
  category: string | null;
  /** The provider label that parsed it (e.g. "Anthropic Claude"), or "Heuristic". */
  engine: string;
}

const SYSTEM =
  "You extract a single structured business event from an SME shopkeeper's plain-language note. Reply with JSON only, no prose or markdown.";

const PROMPT = (text: string) =>
  `Extract one business event from the note and return ONLY a single minified JSON object with exactly these keys:
- eventType: one of "SALE_CREATED" (sold/sale), "PURCHASE_CREATED" (bought/purchased from a supplier), "ORDER_CREATED" (a customer wants/needs something later), "EXPENSE_ADDED" (rent, salary, utilities, fuel, etc.).
- party: the customer or supplier name, or null.
- product: the product name (singular, no unit words like "bags"/"packets"), or null.
- quantity: numeric quantity, or null.
- amount: total money value in rupees if stated, else null.
- category: expense category (e.g. Rent, Utilities) for EXPENSE_ADDED, else null.
Use null where a value is unknown. No extra keys, no commentary.

Note: "${text}"`;

export async function parseCommand(text: string): Promise<ParsedCommand> {
  const provider = getProvider();
  if (provider) {
    try {
      const raw = await provider.complete({ system: SYSTEM, prompt: PROMPT(text), maxTokens: 1024 });
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
  };
}

const UNIT_WORDS =
  /\b(bags?|packets?|pkts?|boxes?|box|pcs?|pieces?|units?|kgs?|kg|kilograms?|grams?|g|litres?|liters?|ltrs?|l|dozens?|cartons?|of|the)\b/gi;

// A dependency-free parser for the common shapes. Good enough as a starting
// point; the confirmation screen lets the user correct anything before publish.
export function heuristicParse(text: string): Omit<ParsedCommand, "engine"> {
  const lower = text.toLowerCase();

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
    return { eventType, party: null, product: null, quantity: null, amount, category };
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
