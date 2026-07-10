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
}

const PROMPT = `Extract this invoice / order slip / WhatsApp screenshot into structured data.
Return ONLY a single minified JSON object with exactly these keys:
- party: the other business or person named, or null.
- docType: "purchase" if this is a bill we received from a supplier, else "sale".
- lineItems: an array of objects, each { "product": string, "quantity": number, "unitPrice": number-or-null }.
- total: the invoice total as a number, or null.
Include every line item. No prose, no markdown, no extra keys.`;

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

  const raw = await provider.complete({
    prompt: PROMPT,
    image: { base64, mediaType },
    maxTokens: 2048,
  });

  const parsed = extractJson<ParsedInvoice>(raw);
  if (!parsed) throw new Error("Could not read a structured invoice from that image.");
  return {
    party: parsed.party ?? null,
    docType: parsed.docType === "purchase" ? "purchase" : "sale",
    lineItems: Array.isArray(parsed.lineItems) ? parsed.lineItems : [],
    total: parsed.total != null ? Number(parsed.total) : null,
  };
}
