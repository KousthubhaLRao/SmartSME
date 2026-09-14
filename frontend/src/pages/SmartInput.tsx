import { useEffect, useRef, useState } from "react";
import { api, useApi, useMutation } from "@/lib/api";
import { PageHeader, PageState } from "@/components/ui/misc";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Icon } from "@/components/Icon";
import { LineItemsEditor, type EditorProduct, type LineRow } from "@/components/LineItemsEditor";
import { cn, toDateInputValue } from "@/lib/utils";

// Typed text survives navigating away and back, until it is actually parsed.
const TEXT_KEY = "smartsme:smart-input:text";
// The parsed, in-progress draft survives navigation too, until it is published.
const DRAFT_KEY = "smartsme:smart-input:draft";

// English, Hinglish, Hindi and Kannada, so it is obvious at a glance that the
// box takes all four. Names and products stay in whatever script they are typed.
const EXAMPLES = [
  "Sold 10 rice bags to Kumar Traders",
  "Kumar Traders ko 10 bori chawal becha",
  "अनीता को 5 किलो चावल बेचा",
  "ಅನಿತಾಗೆ ೪ ಕಿಲೋ ಅಕ್ಕಿ ಮಾರಿದೆ",
  "Paid electricity bill 3200",
];

interface Status {
  hasAI: boolean;
  aiLabel: string | null;
  hasVision: boolean;
  parties: { id: string; name: string; type: string }[];
  products: EditorProduct[];
  taxRate: number;
  currency: string;
}

interface Draft {
  suggestedType: "sale" | "purchase" | "expense";
  engine: string;
  partyId: string | null;
  partyName: string | null;
  items: LineRow[];
  amount: number | null;
  category: string | null;
  discountType: "none" | "amount" | "percentage";
  discountValue: number;
  date: string | null;
  note: string;
}

export function SmartInput() {
  const { data: status, loading, error } = useApi<Status>("/input/status");
  const [mode, setMode] = useState<"text" | "image">("text");
  const [text, setText] = useState("");
  const [preview, setPreview] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const { run, pending, error: parseError, setError } = useMutation();

  // Restore an in-progress draft first (parsed items), else any typed-but-
  // unparsed text, so leaving Smart Input never loses work.
  useEffect(() => {
    try {
      const savedDraft = sessionStorage.getItem(DRAFT_KEY);
      if (savedDraft) {
        const parsed = JSON.parse(savedDraft) as { draft: Draft; mode: "text" | "image" };
        if (parsed?.draft) {
          if (parsed.mode === "image") setMode("image");
          setDraft(parsed.draft);
          return;
        }
      }
      const saved = sessionStorage.getItem(TEXT_KEY);
      if (saved) setText(saved);
    } catch {
      /* sessionStorage unavailable */
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

  function saveDraft(d: Draft, m: "text" | "image" = mode) {
    try {
      sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ draft: d, mode: m }));
    } catch {
      /* ignore */
    }
  }

  function clearStored(key: string) {
    try {
      sessionStorage.removeItem(key);
    } catch {
      /* ignore */
    }
  }

  function reset() {
    setDraft(null);
    setPreview(null);
    setText("");
    clearStored(TEXT_KEY);
    clearStored(DRAFT_KEY);
    if (fileRef.current) fileRef.current.value = "";
  }

  async function parseText() {
    setSuccess(null);
    await run(async () => {
      const res = await api.post<{ draft: Draft }>("/input/parse-text", { text });
      // Parsed: the draft now holds the content, so the raw text no longer
      // needs to persist, but the draft itself does until it is published.
      clearStored(TEXT_KEY);
      saveDraft(res.draft, "text");
      setDraft(res.draft);
    });
  }

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setSuccess(null);
    setPreview(URL.createObjectURL(file));
    await run(async () => {
      const res = await api.upload<{ draft: Draft }>("/input/parse-image", file);
      saveDraft(res.draft, "image");
      setDraft(res.draft);
    });
  }

  if (!status) return <PageState loading={loading} error={error} />;

  if (draft) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Smart Input Engine"
          description="Check what was extracted, then publish. Nothing is saved until you confirm."
        />
        <DraftConfirm
          draft={draft}
          status={status}
          source={mode === "image" ? "ocr" : "nlp"}
          onPersist={(d) => saveDraft(d)}
          onBack={() => {
            clearStored(DRAFT_KEY);
            if (mode === "text") updateText(draft.note);
            setDraft(null);
          }}
          onPublished={(msg) => {
            setSuccess(msg);
            reset();
          }}
        />
      </div>
    );
  }

  const steps = [
    { icon: "input", label: "Type or snap" },
    { icon: "workflow", label: "AI extracts" },
    { icon: "check", label: "You confirm" },
    { icon: "events", label: "Event published" },
  ] as const;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Smart Input Engine"
        description="Turn plain language or a photo into structured business events. You approve before anything is published."
      />

      <Card className="p-4">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {steps.map((s, i) => (
            <div key={s.label} className="flex items-center gap-2">
              <span className="flex items-center gap-2 rounded-full bg-muted px-3 py-1.5 font-medium">
                <Icon name={s.icon} size={15} className="text-link" />
                {s.label}
              </span>
              {i < steps.length - 1 && (
                <Icon name="chevronRight" size={14} className="text-muted-foreground" />
              )}
            </div>
          ))}
        </div>
      </Card>

      {success && (
        <div className="flex items-center gap-2 rounded-lg bg-success/10 px-4 py-3 text-sm text-success">
          <Icon name="check" size={16} /> {success}
        </div>
      )}

      <div className="flex gap-1 rounded-lg border border-border bg-card p-1 text-sm">
        {(["text", "image"] as const).map((m) => (
          <button
            key={m}
            onClick={() => {
              setMode(m);
              setError(null);
            }}
            className={cn(
              "flex flex-1 items-center justify-center gap-2 rounded-md px-3 py-2 font-medium transition-colors",
              mode === m
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:text-foreground",
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
            aria-describedby="smart-input-languages"
            className="min-h-28 text-base"
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === "Enter") parseText();
            }}
          />
          <p id="smart-input-languages" className="mt-2 text-xs text-muted-foreground">
            English, Hindi or Kannada &mdash; in their own script or typed in English letters.
          </p>
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
          <div className="mt-4 flex items-center justify-between gap-3">
            <p className="text-xs text-muted-foreground">
              {status.hasAI
                ? `Parsed by ${status.aiLabel ?? "your AI provider"}.`
                : "Parsed by the built-in engine. Add an API key for smarter parsing."}
            </p>
            <Button onClick={parseText} disabled={pending || !text.trim()}>
              {pending ? "Parsing…" : "Parse"} <Icon name="chevronRight" size={16} />
            </Button>
          </div>
        </Card>
      ) : (
        <Card className="p-5">
          {!status.hasVision && (
            <div className="mb-4 flex items-start gap-2 rounded-lg bg-warning/10 px-3 py-2 text-sm text-warning">
              <Icon name="alert" size={16} className="mt-0.5 shrink-0" />
              <span>
                Image OCR needs an AI provider with vision. Set a vision-capable model in the
                backend environment, then restart the API.
              </span>
            </div>
          )}
          <label
            className={cn(
              "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border px-6 py-10 text-center transition-colors hover:bg-muted/40",
              !status.hasVision && "pointer-events-none opacity-60",
            )}
          >
            <Icon name="products" size={28} className="text-muted-foreground" />
            <span className="text-sm font-medium">
              Upload an invoice, order slip, or WhatsApp screenshot
            </span>
            <span className="text-xs text-muted-foreground">PNG, JPEG, WebP or GIF</span>
            <input
              ref={fileRef}
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              className="hidden"
              onChange={onFile}
              disabled={!status.hasVision}
            />
          </label>
          {preview && (
            <div className="mt-4 flex items-center gap-3">
              <img
                src={preview}
                alt="preview"
                className="h-20 w-20 rounded-lg border border-border object-cover"
              />
              <span className="text-sm text-muted-foreground">
                {pending ? "Reading image…" : "Ready."}
              </span>
            </div>
          )}
        </Card>
      )}

      {parseError && (
        <div className="flex items-start gap-2 rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <Icon name="alert" size={16} className="mt-0.5 shrink-0" /> {parseError}
        </div>
      )}
    </div>
  );
}

function DraftConfirm({
  draft,
  status,
  source,
  onBack,
  onPublished,
  onPersist,
}: {
  draft: Draft;
  status: Status;
  source: "nlp" | "ocr";
  onBack: () => void;
  onPublished: (msg: string) => void;
  onPersist: (d: Draft) => void;
}) {
  const { run, pending, error } = useMutation();
  const [type, setType] = useState<Draft["suggestedType"]>(draft.suggestedType);
  const [partyId, setPartyId] = useState(draft.partyId ?? "");
  const [items, setItems] = useState<LineRow[]>(draft.items);
  const [discountType, setDiscountType] = useState(draft.discountType);
  const [discountValue, setDiscountValue] = useState(draft.discountValue);
  const [date, setDate] = useState(draft.date ?? toDateInputValue());
  const [amountPaid, setAmountPaid] = useState(0);
  const [category, setCategory] = useState(draft.category ?? "General");
  const [amount, setAmount] = useState(draft.amount ?? 0);
  const [description, setDescription] = useState(draft.note);

  const partyList = status.parties.filter(
    (p) => p.type === (type === "purchase" ? "supplier" : "customer"),
  );
  const matchedInList = partyList.some((p) => p.id === draft.partyId);

  // Keep the persisted working draft in sync, so it survives navigating away.
  useEffect(() => {
    onPersist({
      ...draft,
      suggestedType: type,
      partyId: partyId || null,
      items,
      discountType: type === "sale" ? discountType : "none",
      discountValue: type === "sale" ? discountValue : 0,
      date,
    });
    // onPersist/draft are stable; only re-persist when the working values change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [type, partyId, items, discountType, discountValue, date]);

  function changeType(next: Draft["suggestedType"]) {
    setType(next);
    // Drop a selected party that no longer fits the new direction.
    const wanted = next === "purchase" ? "supplier" : "customer";
    setPartyId((cur) => (status.parties.some((p) => p.id === cur && p.type === wanted) ? cur : ""));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const payload =
      type === "expense"
        ? { type, source, category, description, amount, date }
        : {
            type,
            source,
            partyId: partyId || null,
            items: items.filter((i) => i.description.trim() && i.quantity > 0),
            amountPaid,
            discountType: type === "sale" ? discountType : "none",
            discountValue: type === "sale" ? discountValue : 0,
            date,
          };
    await run(async () => {
      const res = await api.post<{ ok: string }>("/input/publish", payload);
      onPublished(res.ok);
    });
  }

  return (
    <Card className="p-5">
      <div className="mb-4 flex items-center justify-between">
        <button
          onClick={onBack}
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <Icon name="chevronRight" size={16} className="rotate-180" /> Edit input
        </button>
        <Badge tone={draft.engine !== "Heuristic" ? "primary" : "default"}>
          {draft.engine} · {source === "ocr" ? "OCR" : "Text"}
        </Badge>
      </div>

      <div className="mb-4 rounded-lg bg-muted/50 px-3 py-2 text-sm text-muted-foreground">
        <span className="font-medium text-foreground">Detected:</span> {draft.note}
        {draft.partyName && !matchedInList && (
          <div className="mt-1 text-xs text-warning">
            “{draft.partyName}” is not in your parties yet. Pick one below or add it later.
          </div>
        )}
      </div>

      <form onSubmit={submit} className="flex flex-col gap-4">
        <Field label="Record as">
          <Select
            value={type}
            onChange={(e) => changeType(e.target.value as Draft["suggestedType"])}
          >
            <option value="sale">Sale</option>
            <option value="purchase">Purchase</option>
            <option value="expense">Expense</option>
          </Select>
        </Field>

        <Field
          label="Date"
          hint={
            draft.date
              ? "Picked up from your note. Change it if that is wrong."
              : "Defaults to today. Back-date it if this happened earlier."
          }
        >
          <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </Field>

        {type === "expense" ? (
          <>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Category">
                <Input value={category} onChange={(e) => setCategory(e.target.value)} />
              </Field>
              <Field label="Amount">
                <Input
                  type="number"
                  min={0}
                  step="0.01"
                  value={amount || ""}
                  onChange={(e) => setAmount(Number(e.target.value) || 0)}
                />
              </Field>
            </div>
            <Field label="Description">
              <Input
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                required
              />
            </Field>
          </>
        ) : (
          <>
            <Field label={type === "purchase" ? "Supplier" : "Customer"}>
              <Select value={partyId} onChange={(e) => setPartyId(e.target.value)}>
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
              products={status.products}
              priceField={type === "purchase" ? "purchasePrice" : "sellingPrice"}
              taxRate={status.taxRate}
              currency={status.currency}
              initialRows={draft.items}
              discountType={type === "sale" ? discountType : "none"}
              discountValue={type === "sale" ? discountValue : 0}
              onChange={setItems}
            />

            {type === "sale" && (
              <div className="grid gap-3 md:grid-cols-2">
                <Field label="Discount type">
                  <Select
                    value={discountType}
                    onChange={(e) => setDiscountType(e.target.value as Draft["discountType"])}
                  >
                    <option value="none">No discount</option>
                    <option value="amount">Amount</option>
                    <option value="percentage">Percentage</option>
                  </Select>
                </Field>
                <Field
                  label="Discount value"
                  hint="Enter amount or % depending on the selected type."
                >
                  <Input
                    type="number"
                    min={0}
                    step="0.01"
                    value={discountValue || ""}
                    onChange={(e) => setDiscountValue(Number(e.target.value) || 0)}
                  />
                </Field>
              </div>
            )}

            <Field label="Amount paid" hint="Leave 0 to keep it as credit.">
              <Input
                type="number"
                min={0}
                step="0.01"
                value={amountPaid || ""}
                onChange={(e) => setAmountPaid(Number(e.target.value) || 0)}
              />
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
