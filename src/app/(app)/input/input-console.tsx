"use client";

import { useEffect, useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Icon } from "@/components/icons";
import { LineItemsEditor, type EditorProduct } from "@/components/line-items-editor";
import { cn } from "@/lib/utils";
import { parseTextAction, parseImageAction, publishDraftAction, type Draft } from "./actions";

interface Party {
  id: string;
  name: string;
  type: string;
}

const EXAMPLES = [
  "Sold 10 rice bags to Kumar Traders",
  "Purchase 50 sugar packets from ABC Suppliers",
  "Paid electricity bill 3200",
  "Anita Stores wants 5 flour bags",
];

// Draft text survives navigating away and back (until it's actually parsed).
const TEXT_KEY = "smartsme:smart-input:text";
// The parsed, in-progress draft survives navigation too (until it's published).
const DRAFT_KEY = "smartsme:smart-input:draft";

export function InputConsole({
  parties,
  products,
  currency,
  taxRate,
  hasAI,
  aiLabel,
}: {
  parties: Party[];
  products: EditorProduct[];
  currency: string;
  taxRate: number;
  hasAI: boolean;
  aiLabel?: string | null;
}) {
  const [mode, setMode] = useState<"text" | "image">("text");
  const [text, setText] = useState("");
  const [preview, setPreview] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const fileRef = useRef<HTMLInputElement>(null);

  const draftSource = (): "nlp" | "ocr" => (mode === "image" ? "ocr" : "nlp");

  // Restore an in-progress draft first (parsed items), else any typed-but-unparsed
  // text — so leaving Smart Input and coming back never loses work.
  useEffect(() => {
    try {
      const savedDraft = sessionStorage.getItem(DRAFT_KEY);
      if (savedDraft) {
        const parsed = JSON.parse(savedDraft) as { draft: Draft; source: "nlp" | "ocr" };
        if (parsed?.draft) {
          if (parsed.source === "ocr") setMode("image");
          setDraft(parsed.draft);
          return;
        }
      }
      const saved = sessionStorage.getItem(TEXT_KEY);
      if (saved) setText(saved);
    } catch {
      /* sessionStorage unavailable — ignore */
    }
  }, []);

  function updateText(v: string) {
    setText(v);
    try {
      sessionStorage.setItem(TEXT_KEY, v);
    } catch {
      /* ignore */
    }
  }

  function clearSavedText() {
    try {
      sessionStorage.removeItem(TEXT_KEY);
    } catch {
      /* ignore */
    }
  }

  function saveDraft(d: Draft) {
    try {
      sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ draft: d, source: draftSource() }));
    } catch {
      /* ignore */
    }
  }

  function clearSavedDraft() {
    try {
      sessionStorage.removeItem(DRAFT_KEY);
    } catch {
      /* ignore */
    }
  }

  function reset() {
    setDraft(null);
    setError(null);
    setPreview(null);
    setText("");
    clearSavedText();
    clearSavedDraft();
    if (fileRef.current) fileRef.current.value = "";
  }

  function parseText() {
    setError(null);
    setSuccess(null);
    start(async () => {
      try {
        const res = await parseTextAction(text);
        if (res.error) setError(res.error);
        else {
          // Parsed: the draft now holds the content, so the raw text no longer
          // needs to persist — but the draft itself does, until it's published.
          clearSavedText();
          saveDraft(res.draft!);
          setDraft(res.draft!);
        }
      } catch {
        setError("Could not reach the server. Please try again.");
      }
    });
  }

  function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setSuccess(null);
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = String(reader.result);
      setPreview(dataUrl);
      start(async () => {
        try {
          const res = await parseImageAction(dataUrl);
          if (res.error) setError(res.error);
          else {
            saveDraft(res.draft!);
            setDraft(res.draft!);
          }
        } catch {
          setError("Could not process that image. It may be too large. Try a smaller photo.");
        }
      });
    };
    reader.onerror = () => setError("Could not read that file.");
    reader.readAsDataURL(file);
  }

  if (draft) {
    return (
      <DraftConfirm
        draft={draft}
        parties={parties}
        products={products}
        currency={currency}
        taxRate={taxRate}
        source={mode === "image" ? "ocr" : "nlp"}
        onBack={() => {
          // Going back to edit the command discards the parsed draft, but keeps
          // the original text so it can be tweaked and re-parsed.
          clearSavedDraft();
          if (mode === "text") updateText(draft.note);
          setDraft(null);
        }}
        onPersist={saveDraft}
        onPublished={(msg) => {
          setSuccess(msg);
          reset();
        }}
      />
    );
  }

  return (
    <div className="space-y-4">
      {success && (
        <div className="flex items-center gap-2 rounded-lg bg-success/10 px-4 py-3 text-sm text-success">
          <Icon name="check" size={16} /> {success}
        </div>
      )}

      <div className="flex gap-1 rounded-lg border border-border bg-card p-1 text-sm">
        {(["text", "image"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={cn(
              "flex flex-1 items-center justify-center gap-2 rounded-md px-3 py-2 font-medium transition-colors",
              mode === m ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Icon name={m === "text" ? "input" : "products"} size={16} />
            {m === "text" ? "Natural language" : "Image / OCR"}
          </button>
        ))}
      </div>

      {mode === "text" ? (
        <Card className="p-5">
          <Textarea
            value={text}
            onChange={(e) => updateText(e.target.value)}
            placeholder="e.g. Sold 10 rice bags to Kumar Traders"
            className="min-h-28 text-base"
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === "Enter") parseText();
            }}
          />
          <div className="mt-3 flex flex-wrap gap-2">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                onClick={() => updateText(ex)}
                className="rounded-full border border-border px-3 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                {ex}
              </button>
            ))}
          </div>
          <div className="mt-4 flex items-center justify-between">
            <p className="text-xs text-muted-foreground">
              {hasAI ? `Parsed by ${aiLabel ?? "your AI provider"}.` : "Parsed by the built-in engine. Add an API key for smarter parsing."}
            </p>
            <Button onClick={parseText} disabled={pending || !text.trim()}>
              {pending ? "Parsing…" : "Parse"} <Icon name="chevronRight" size={16} />
            </Button>
          </div>
        </Card>
      ) : (
        <Card className="p-5">
          {!hasAI && (
            <div className="mb-4 flex items-start gap-2 rounded-lg bg-warning/10 px-3 py-2 text-sm text-warning">
              <Icon name="alert" size={16} className="mt-0.5 shrink-0" />
              <span>Image OCR needs an AI provider with vision. Add an API key (<code>ANTHROPIC_API_KEY</code>, <code>OPENAI_API_KEY</code>, or <code>GOOGLE_API_KEY</code>) to <code>.env</code>, then restart.</span>
            </div>
          )}
          <label
            className={cn(
              "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border px-6 py-10 text-center transition-colors hover:bg-muted/40",
              !hasAI && "pointer-events-none opacity-60",
            )}
          >
            <Icon name="products" size={28} className="text-muted-foreground" />
            <span className="text-sm font-medium">Upload an invoice, order slip, or WhatsApp screenshot</span>
            <span className="text-xs text-muted-foreground">PNG, JPEG, WebP or GIF</span>
            <input
              ref={fileRef}
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              className="hidden"
              onChange={onFile}
              disabled={!hasAI}
            />
          </label>
          {preview && (
            <div className="mt-4 flex items-center gap-3">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={preview} alt="preview" className="h-20 w-20 rounded-lg border border-border object-cover" />
              <span className="text-sm text-muted-foreground">{pending ? "Reading image…" : "Ready."}</span>
            </div>
          )}
        </Card>
      )}

      {error && (
        <div className="flex items-start gap-2 rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <Icon name="alert" size={16} className="mt-0.5 shrink-0" /> {error}
        </div>
      )}
    </div>
  );
}

function DraftConfirm({
  draft,
  parties,
  products,
  currency,
  taxRate,
  source,
  onBack,
  onPublished,
  onPersist,
}: {
  draft: Draft;
  parties: Party[];
  products: EditorProduct[];
  currency: string;
  taxRate: number;
  source: "nlp" | "ocr";
  onBack: () => void;
  onPublished: (msg: string) => void;
  onPersist: (draft: Draft) => void;
}) {
  const partyTypeFor = (t: Draft["suggestedType"]) => (t === "purchase" ? "supplier" : "customer");
  const [type, setType] = useState<Draft["suggestedType"]>(draft.suggestedType);
  const [discountType, setDiscountType] = useState<Draft["discountType"]>(
    draft.discountType === "none" ? "percentage" : draft.discountType,
  );
  const [discountValue, setDiscountValue] = useState<number>(draft.discountValue);
  const [partyId, setPartyId] = useState<string>(
    draft.partyId && parties.some((p) => p.id === draft.partyId && p.type === partyTypeFor(draft.suggestedType))
      ? draft.partyId
      : "",
  );
  const [items, setItems] = useState<Draft["items"]>(draft.items);
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const router = useRouter();

  const partyList = parties.filter((p) => p.type === partyTypeFor(type));
  const priceField = type === "purchase" ? "purchasePrice" : "sellingPrice";
  const matchedInList = partyList.some((p) => p.id === draft.partyId);

  function changeType(next: Draft["suggestedType"]) {
    setType(next);
    // Drop a selected party that no longer fits the new direction.
    setPartyId((cur) => (parties.some((p) => p.id === cur && p.type === partyTypeFor(next)) ? cur : ""));
  }

  // Keep the persisted working draft in sync so it survives navigating away.
  useEffect(() => {
    onPersist({
      ...draft,
      suggestedType: type,
      partyId: partyId || null,
      items,
      discountType: type === "expense" ? "none" : discountType,
      discountValue: type === "expense" ? 0 : discountValue,
    });
    // onPersist/draft are stable; only re-persist when the working values change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [type, partyId, items, discountType, discountValue]);

  function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    setError(null);
    start(async () => {
      const res = await publishDraftAction(fd);
      if (res.error) setError(res.error);
      else {
        router.refresh();
        onPublished(res.ok ?? "Recorded.");
      }
    });
  }

  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            onClick={onBack}
            className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <Icon name="chevronRight" size={16} className="rotate-180" /> Edit input
          </button>
        </div>
        <Badge tone={draft.engine !== "Heuristic" ? "primary" : "default"}>
          {draft.engine} · {source === "ocr" ? "OCR" : "Text"}
        </Badge>
      </div>

      <div className="mb-4 rounded-lg bg-muted/50 px-3 py-2 text-sm text-muted-foreground">
        <span className="font-medium text-foreground">Detected:</span> {draft.note}
        {draft.partyName && !matchedInList && (
          <div className="mt-1 text-xs text-warning">
            “{draft.partyName}” isn’t in your parties yet. Pick one below or add it later.
          </div>
        )}
      </div>

      <form onSubmit={submit} className="flex flex-col gap-4">
        <input type="hidden" name="source" value={source} />
        <input type="hidden" name="type" value={type} />

        <Field label="Record as">
          <Select value={type} onChange={(e) => changeType(e.target.value as Draft["suggestedType"])}>
            <option value="sale">Sale</option>
            <option value="purchase">Purchase</option>
            <option value="expense">Expense</option>
          </Select>
        </Field>

        {type === "expense" ? (
          <>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Category">
                <Input name="category" defaultValue={draft.category ?? "General"} />
              </Field>
              <Field label="Amount ₹">
                <Input name="amount" type="number" min={0} step="0.01" defaultValue={draft.amount ?? 0} />
              </Field>
            </div>
            <Field label="Description">
              <Input name="description" defaultValue={draft.note} required />
            </Field>
          </>
        ) : (
          <>
            <Field label={type === "purchase" ? "Supplier" : "Customer"}>
              <Select name="partyId" value={partyId} onChange={(e) => setPartyId(e.target.value)}>
                <option value="">{type === "purchase" ? "None" : "Walk-in / none"}</option>
                {partyList.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </Select>
            </Field>
            <LineItemsEditor
              key={type}
              products={products}
              priceField={priceField}
              taxRate={taxRate}
              currency={currency}
              initialRows={draft.items}
              discountType={discountType}
              discountValue={discountValue}
              onRowsChange={(rows) =>
                setItems(
                  rows.map((r) => ({
                    productId: r.productId ?? null,
                    description: r.description,
                    quantity: r.quantity,
                    unitPrice: r.unitPrice,
                  })),
                )
              }
            />
            <div className="grid gap-3 md:grid-cols-2">
              <Field label="Discount type">
                <Select
                  name="discountType"
                  value={discountType}
                  onChange={(e) => setDiscountType(e.target.value as Draft["discountType"])}
                >
                  <option value="percentage">Percentage</option>
                  <option value="amount">Amount</option>
                </Select>
              </Field>
              <Field label="Discount" hint={discountType === "amount" ? "Enter the discount amount." : "Enter the discount percentage."}>
                <Input
                  name="discountValue"
                  type="number"
                  min={0}
                  step="0.01"
                  value={discountValue || ""}
                  onChange={(e) => setDiscountValue(Number(e.target.value) || 0)}
                  placeholder={discountType === "amount" ? "20" : "10"}
                />
              </Field>
            </div>
            <Field label="Amount paid" hint="Leave 0 to keep it as credit.">
              <Input name="amountPaid" type="number" min={0} step="0.01" defaultValue={0} />
            </Field>
          </>
        )}

        {error && <p className="text-sm text-destructive">{error}</p>}

        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onBack} disabled={pending}>
            Back
          </Button>
          <Button type="submit" disabled={pending}>
            <Icon name="check" size={16} /> {pending ? "Publishing…" : "Confirm & publish"}
          </Button>
        </div>
      </form>
    </Card>
  );
}
