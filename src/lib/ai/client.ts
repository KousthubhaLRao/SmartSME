import Anthropic from "@anthropic-ai/sdk";

/**
 * Provider-agnostic AI layer for the Smart Input engine. It works with whichever
 * API key you set, with no code changes needed to switch provider:
 *
 *   - Anthropic:  ANTHROPIC_API_KEY            (+ optional ANTHROPIC_MODEL)
 *   - Groq:       GROQ_API_KEY                 (+ optional GROQ_MODEL)
 *   - OpenAI, or ANY OpenAI-compatible endpoint (OpenRouter, Together, DeepSeek,
 *     Mistral, a local server, ...):  OPENAI_API_KEY
 *       + optional OPENAI_BASE_URL   (default https://api.openai.com/v1)
 *       + optional OPENAI_MODEL      (default gpt-4o-mini)
 *   - Google Gemini:  GOOGLE_API_KEY or GEMINI_API_KEY  (+ optional GEMINI_MODEL)
 *
 * If several keys are set, AI_PROVIDER=anthropic|openai|groq|google picks one;
 * otherwise the first configured provider (in the order above) is used. When no
 * key is set at all, callers fall back to the built-in heuristic parser.
 */

export interface AiImage {
  base64: string;
  mediaType: string; // e.g. "image/png"
}

export interface AiRequest {
  system?: string;
  prompt: string;
  image?: AiImage;
  maxTokens?: number;
}

export type ProviderId = "anthropic" | "openai" | "groq" | "google";

export interface AiProvider {
  id: ProviderId;
  label: string;
  model: string;
  vision: boolean;
  /** Runs the model and returns its raw text (expected to contain a JSON object). */
  complete(req: AiRequest): Promise<string>;
}

function forcedProvider(): ProviderId | null {
  const v = (process.env.AI_PROVIDER || "").toLowerCase().trim();
  return v === "anthropic" || v === "openai" || v === "groq" || v === "google" ? v : null;
}

// ---- Anthropic --------------------------------------------------------------
function anthropic(): AiProvider | null {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) return null;
  const model = process.env.ANTHROPIC_MODEL || "claude-opus-4-8";
  const client = new Anthropic({ apiKey });
  return {
    id: "anthropic",
    label: "Anthropic Claude",
    model,
    vision: true,
    async complete(req) {
      const content: Array<Record<string, unknown>> = [];
      if (req.image) {
        content.push({
          type: "image",
          source: { type: "base64", media_type: req.image.mediaType, data: req.image.base64 },
        });
      }
      content.push({ type: "text", text: req.prompt });
      // Cast keeps us decoupled from the installed SDK's exact param types.
      const res = (await client.messages.create({
        model,
        max_tokens: req.maxTokens ?? 1024,
        system: req.system,
        messages: [{ role: "user", content }],
      } as never)) as { content?: Array<{ type: string; text?: string }> };
      return (res.content ?? []).map((b) => (b.type === "text" ? b.text ?? "" : "")).join("");
    },
  };
}

// ---- OpenAI / any OpenAI-compatible endpoint (incl. Groq) -------------------
// Shared chat-completions implementation. Groq, OpenRouter, Together, a local
// server, etc. all speak this same wire format; only the base URL/model differ.
function openAiCompatible(opts: {
  id: ProviderId;
  label: string;
  apiKey: string;
  baseUrl: string;
  model: string;
  vision: boolean;
}): AiProvider {
  const baseUrl = opts.baseUrl.replace(/\/+$/, "");
  return {
    id: opts.id,
    label: opts.label,
    model: opts.model,
    vision: opts.vision,
    async complete(req) {
      const messages: Array<Record<string, unknown>> = [];
      if (req.system) messages.push({ role: "system", content: req.system });
      messages.push({
        role: "user",
        content: req.image
          ? [
              { type: "text", text: req.prompt },
              {
                type: "image_url",
                image_url: { url: `data:${req.image.mediaType};base64,${req.image.base64}` },
              },
            ]
          : req.prompt,
      });
      const res = await fetch(`${baseUrl}/chat/completions`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${opts.apiKey}` },
        body: JSON.stringify({ model: opts.model, messages, max_tokens: req.maxTokens ?? 1024 }),
      });
      if (!res.ok) {
        throw new Error(`AI request failed (${res.status}). ${(await res.text()).slice(0, 200)}`);
      }
      const data = (await res.json()) as { choices?: Array<{ message?: { content?: string } }> };
      return data.choices?.[0]?.message?.content ?? "";
    },
  };
}

function openai(): AiProvider | null {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) return null;
  return openAiCompatible({
    id: "openai",
    label: "OpenAI-compatible",
    apiKey,
    baseUrl: process.env.OPENAI_BASE_URL || "https://api.openai.com/v1",
    model: process.env.OPENAI_MODEL || "gpt-4o-mini",
    vision: true,
  });
}

function groq(): AiProvider | null {
  const apiKey = process.env.GROQ_API_KEY;
  if (!apiKey) return null;
  // Groq offers both fast text models and vision-capable ones. The default is a
  // strong text model; set GROQ_MODEL to a vision model to use image OCR.
  return openAiCompatible({
    id: "groq",
    label: "Groq",
    apiKey,
    baseUrl: process.env.GROQ_BASE_URL || "https://api.groq.com/openai/v1",
    model: process.env.GROQ_MODEL || "llama-3.3-70b-versatile",
    vision: true,
  });
}

// ---- Google Gemini ----------------------------------------------------------
function google(): AiProvider | null {
  const apiKey = process.env.GOOGLE_API_KEY || process.env.GEMINI_API_KEY;
  if (!apiKey) return null;
  const model = process.env.GEMINI_MODEL || process.env.GOOGLE_MODEL || "gemini-2.0-flash";
  return {
    id: "google",
    label: "Google Gemini",
    model,
    vision: true,
    async complete(req) {
      const parts: Array<Record<string, unknown>> = [
        { text: req.system ? `${req.system}\n\n${req.prompt}` : req.prompt },
      ];
      if (req.image) parts.push({ inlineData: { mimeType: req.image.mediaType, data: req.image.base64 } });
      const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`;
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contents: [{ role: "user", parts }],
          generationConfig: { maxOutputTokens: req.maxTokens ?? 1024, responseMimeType: "application/json" },
        }),
      });
      if (!res.ok) {
        throw new Error(`AI request failed (${res.status}). ${(await res.text()).slice(0, 200)}`);
      }
      const data = (await res.json()) as {
        candidates?: Array<{ content?: { parts?: Array<{ text?: string }> } }>;
      };
      return (data.candidates?.[0]?.content?.parts ?? []).map((p) => p.text ?? "").join("");
    },
  };
}

const BUILDERS: Record<ProviderId, () => AiProvider | null> = { anthropic, openai, groq, google };
const ORDER: ProviderId[] = ["anthropic", "openai", "groq", "google"];

/** The active provider, or null when no API key is configured. */
export function getProvider(): AiProvider | null {
  const forced = forcedProvider();
  if (forced) return BUILDERS[forced]();
  for (const id of ORDER) {
    const p = BUILDERS[id]();
    if (p) return p;
  }
  return null;
}

/** True when any AI provider is configured. */
export function hasAI(): boolean {
  return getProvider() !== null;
}

/** True when the active provider can read images (for OCR). */
export function hasVision(): boolean {
  const p = getProvider();
  return p !== null && p.vision;
}

/** Display info for settings/UI, or null when unconfigured. */
export function aiStatus(): { id: ProviderId; label: string; model: string; vision: boolean } | null {
  const p = getProvider();
  return p ? { id: p.id, label: p.label, model: p.model, vision: p.vision } : null;
}

/** Pull the first JSON object out of a model's text response. */
export function extractJson<T>(text: string): T | null {
  try {
    const start = text.indexOf("{");
    const end = text.lastIndexOf("}");
    if (start === -1 || end === -1) return null;
    return JSON.parse(text.slice(start, end + 1)) as T;
  } catch {
    return null;
  }
}
