import { extractJson, getProvider } from "./client";

export interface ParsedInvoiceLine {
  product: string;
  quantity: number;
  unitPrice: number | null;
}

export interface ParsedInvoice {
  party: string | null;
  docType: "sale" | "purchase";
  lineItems: ParsedInvoiceLine[];
  total: number | null;
  /** Document date as YYYY-MM-DD when the image shows one, else null. */
  date: string | null;
  /** A discount printed on the document. */
  discountType: "none" | "amount" | "percentage";
  discountValue: number;
}

const SYSTEM =
  "You read an SME invoice, order slip, or handwritten note from an image and return structured data. Reply with JSON only, no prose or markdown.";

const PROMPT = (todayIso: string) =>
  `Extract this invoice / order slip / WhatsApp screenshot into structured data.
Return ONLY a single minified JSON object with exactly these keys:
- party: the other business or person named, or null.
- docType: "purchase" if this is a bill we received from a supplier, else "sale".
- lineItems: an array of objects, each { "product": string, "quantity": number, "unitPrice": number-or-null }.
- total: the document total as a number, or null.
- date: the date printed on the document as "YYYY-MM-DD", or null if none is shown. Today is ${todayIso}; resolve relative wording against it, and read day-first formats (20/08/2026 means 20 August 2026).
- discountType: "percentage" if a percentage discount is shown, "amount" if a flat money discount is shown, otherwise "none".
- discountValue: the numeric discount (the percent number, or the money figure); 0 when discountType is "none".
Include every line item. Use null where a value is unknown. No extra keys, no commentary.`;

/**
 * Reads an invoice / order-slip / WhatsApp screenshot into structured data using
 * whichever configured AI provider supports vision (Anthropic, OpenAI-compatible,
 * or Gemini). There is no offline fallback for image OCR.
 */
export async function parseInvoiceImage(
  base64: string,
  mediaType: "image/png" | "image/jpeg" | "image/webp" | "image/gif",
): Promise<ParsedInvoice> {
  const provider = getProvider();
  if (!provider || !provider.vision) {
    throw new Error(
      "Image OCR needs an AI provider that can read images. Set an API key (ANTHROPIC_API_KEY, OPENAI_API_KEY, or GOOGLE_API_KEY), or use text/manual input instead.",
    );
  }

  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  const todayIso = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;

  const raw = await provider.complete({
    system: SYSTEM,
    prompt: PROMPT(todayIso),
    image: { base64, mediaType },
    maxTokens: 2048,
  });

  const parsed = extractJson<ParsedInvoice>(raw);
  if (!parsed) throw new Error("Could not read a structured invoice from that image.");

  const discountValue = parsed.discountValue != null ? Number(parsed.discountValue) : 0;
  return {
    party: parsed.party ?? null,
    docType: parsed.docType === "purchase" ? "purchase" : "sale",
    lineItems: Array.isArray(parsed.lineItems) ? parsed.lineItems : [],
    total: parsed.total != null ? Number(parsed.total) : null,
    date:
      typeof parsed.date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(parsed.date) ? parsed.date : null,
    discountType:
      parsed.discountType === "amount" || parsed.discountType === "percentage"
        ? parsed.discountType
        : "none",
    discountValue: Number.isFinite(discountValue) && discountValue > 0 ? discountValue : 0,
  };
}
