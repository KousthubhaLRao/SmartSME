import { useState } from "react";
import { api, useApi, useMutation } from "@/lib/api";
import { PageHeader, PageState, SectionCard } from "@/components/ui/misc";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Icon } from "@/components/Icon";
import { Can, PERMISSIONS } from "@/lib/session";

interface SettingsData {
  business: {
    name: string;
    gstNumber: string | null;
    panNumber: string | null;
    address: string | null;
    phone: string | null;
    email: string | null;
    currency: string;
    taxRate: number;
    invoicePrefix: string;
  };
  ai: { id: string; label: string; model: string; vision: boolean } | null;
}

const CURRENCIES = ["INR", "USD", "EUR", "GBP"];

export function Settings() {
  const { data, loading, error, reload } = useApi<SettingsData>("/settings");
  const { run, pending, error: saveError } = useMutation();
  const [form, setForm] = useState<SettingsData["business"] | null>(null);
  const [saved, setSaved] = useState(false);

  // Seed the form once the business loads.
  if (data && form === null) setForm(data.business);
  if (!data || !form) return <PageState loading={loading} error={error} />;

  const text =
    (k: keyof SettingsData["business"]) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
      setSaved(false);
      setForm((f) => (f ? { ...f, [k]: e.target.value } : f));
    };

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!form) return;
    const ok = await run(
      () => api.put("/settings", { ...form, taxRate: Number(form.taxRate) }),
      reload,
    );
    if (ok) setSaved(true);
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Settings" description="Business profile, tax and invoicing defaults." />

      <SectionCard title="Business profile" description="Appears on your invoices">
        <form onSubmit={submit} className="flex flex-col gap-4 p-5">
          <Field label="Business name">
            <Input value={form.name} onChange={text("name")} required />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="GSTIN">
              <Input
                value={form.gstNumber ?? ""}
                onChange={text("gstNumber")}
                placeholder="29ABCDE1234F1Z5"
              />
            </Field>
            <Field label="PAN">
              <Input
                value={form.panNumber ?? ""}
                onChange={text("panNumber")}
                placeholder="ABCDE1234F"
              />
            </Field>
          </div>
          <Field label="Address">
            <Textarea
              value={form.address ?? ""}
              onChange={text("address")}
              placeholder="Shop address"
            />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Phone">
              <Input value={form.phone ?? ""} onChange={text("phone")} />
            </Field>
            <Field label="Email">
              <Input type="email" value={form.email ?? ""} onChange={text("email")} />
            </Field>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Currency">
              <Select value={form.currency} onChange={text("currency")}>
                {CURRENCIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Tax rate (%)" hint="Applied to new sales and purchases.">
              <Input
                type="number"
                min={0}
                max={100}
                step="0.01"
                value={form.taxRate}
                onChange={text("taxRate")}
              />
            </Field>
            <Field label="Invoice prefix">
              <Input
                value={form.invoicePrefix}
                onChange={text("invoicePrefix")}
                placeholder="INV"
              />
            </Field>
          </div>

          {saveError && <p className="text-sm text-destructive">{saveError}</p>}
          <div className="flex items-center justify-end gap-3">
            {saved && (
              <span className="flex items-center gap-1 text-sm text-success">
                <Icon name="check" size={15} /> Saved
              </span>
            )}
            <Can do={PERMISSIONS.configWrite}>
              <Button type="submit" disabled={pending}>
                {pending ? "Saving…" : "Save changes"}
              </Button>
            </Can>
          </div>
        </form>
      </SectionCard>

      <SectionCard title="AI provider" description="Powers natural-language parsing and image OCR">
        <div className="space-y-3 p-5 text-sm">
          {data.ai ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="primary">{data.ai.label}</Badge>
                <span className="text-muted-foreground">{data.ai.model}</span>
                {data.ai.vision ? (
                  <Badge tone="success">Vision: OCR available</Badge>
                ) : (
                  <Badge tone="warning">Text only: OCR unavailable</Badge>
                )}
              </div>
              {!data.ai.vision && (
                <p className="text-muted-foreground">
                  This model cannot read images. Switch to a vision-capable model to use Image / OCR
                  input.
                </p>
              )}
            </>
          ) : (
            <div className="flex items-start gap-2 rounded-lg bg-warning/10 px-3 py-2 text-warning">
              <Icon name="alert" size={16} className="mt-0.5 shrink-0" />
              <span>
                No AI provider configured. Text input falls back to the built-in regex parser.
                Photographed orders need either GOOGLE_API_KEY (free, and the only option that
                reads a crossed-out line) or OCR_SPACE_API_KEY (free). Set one in the backend
                environment and restart the API.
              </span>
            </div>
          )}
        </div>
      </SectionCard>
    </div>
  );
}
