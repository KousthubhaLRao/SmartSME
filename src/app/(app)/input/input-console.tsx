"use client";

import { useRef, useState, useTransition } from "react";
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

  function reset() {
    setDraft(null);
    setError(null);
    setPreview(null);
    setText("");
    if (fileRef.current) fileRef.current.value = "";
  }

  function parseText() {
    setError(null);
    setSuccess(null);
    start(async () => {
      try {
        const res = await parseTextAction(text);
        if (res.error) setError(res.error);
        else setDraft(res.draft!);
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
          else setDraft(res.draft!);
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
        onBack={() => setDraft(null)}
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
            onChange={(e) => setText(e.target.value)}
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
                onClick={() => setText(ex)}
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
}: {
  draft: Draft;
  parties: Party[];
  products: EditorProduct[];
  currency: string;
  taxRate: number;
  source: "nlp" | "ocr";
  onBack: () => void;
  onPublished: (msg: string) => void;
}) {
  const [type, setType] = useState<Draft["suggestedType"]>(draft.suggestedType);
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const router = useRouter();

  const partyList = parties.filter((p) => p.type === (type === "purchase" ? "supplier" : "customer"));
  const priceField = type === "purchase" ? "purchasePrice" : "sellingPrice";
  const matchedInList = partyList.some((p) => p.id === draft.partyId);

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
          <Select value={type} onChange={(e) => setType(e.target.value as Draft["suggestedType"])}>
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
              <Select name="partyId" defaultValue={matchedInList ? draft.partyId! : ""}>
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
            />
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
