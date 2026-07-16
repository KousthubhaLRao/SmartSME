"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { LineItemsEditor, type EditorProduct } from "@/components/line-items-editor";
import { Icon } from "@/components/icons";
import { createSaleAction } from "./actions";

export function NewSaleDialog({
  parties,
  products,
  currency,
  taxRate,
}: {
  parties: { id: string; name: string }[];
  products: EditorProduct[];
  currency: string;
  taxRate: number;
}) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const router = useRouter();

  function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    setError(null);
    start(async () => {
      const res = await createSaleAction(fd);
      if (res.error) setError(res.error);
      else {
        setOpen(false);
        router.refresh();
      }
    });
  }

  return (
    <>
      <Button onClick={() => setOpen(true)}>
        <Icon name="plus" size={16} /> New sale
      </Button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="New sale"
        description="Create an invoice. Inventory and balances update automatically via the event bus."
      >
        <form onSubmit={submit} className="flex flex-col gap-4">
          <Field label="Customer">
            <Select name="partyId" defaultValue="">
              <option value="">Walk-in / none</option>
              {parties.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
          </Field>
          <LineItemsEditor
            products={products}
            priceField="sellingPrice"
            taxRate={taxRate}
            currency={currency}
          />
          <div className="grid gap-3 md:grid-cols-2">
            <Field label="Discount type">
              <Select name="discountType" defaultValue="none">
                <option value="none">No discount</option>
                <option value="amount">Amount</option>
                <option value="percentage">Percentage</option>
              </Select>
            </Field>
            <Field label="Discount value" hint="Enter amount or % depending on the selected type.">
              <Input name="discountValue" type="number" min={0} step="0.01" defaultValue={0} />
            </Field>
          </div>
          <Field label="Amount paid" hint="Leave 0 for a credit sale (unpaid).">
            <Input name="amountPaid" type="number" min={0} step="0.01" defaultValue={0} />
          </Field>
          <Field label="Notes">
            <Textarea name="notes" placeholder="Optional" />
          </Field>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setOpen(false)} disabled={pending}>
              Cancel
            </Button>
            <Button type="submit" disabled={pending}>
              {pending ? "Creating…" : "Create sale"}
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
