"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { LineItemsEditor, type EditorProduct } from "@/components/line-items-editor";
import { Icon } from "@/components/icons";
import { createPurchaseAction } from "./actions";

export function NewPurchaseDialog({
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
  const [discountType, setDiscountType] = useState<"amount" | "percentage">("percentage");
  const [discountValue, setDiscountValue] = useState(0);
  const [pending, start] = useTransition();
  const router = useRouter();

  function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    setError(null);
    start(async () => {
      const res = await createPurchaseAction(fd);
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
        <Icon name="plus" size={16} /> New purchase
      </Button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="New purchase"
        description="Record a supplier bill. Stock is received automatically."
      >
        <form onSubmit={submit} className="flex flex-col gap-4">
          <Field label="Supplier">
            <Select name="partyId" defaultValue="">
              <option value="">None</option>
              {parties.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
          </Field>
          <LineItemsEditor
            products={products}
            priceField="purchasePrice"
            taxRate={taxRate}
            currency={currency}
            discountType={discountType}
            discountValue={discountValue}
          />
          <div className="grid gap-3 md:grid-cols-2">
            <Field label="Discount type">
              <Select name="discountType" value={discountType} onChange={(e) => setDiscountType(e.target.value as "amount" | "percentage")}>
                <option value="percentage">Percentage</option>
                <option value="amount">Amount</option>
              </Select>
            </Field>
            <Field label="Discount" hint={discountType === "amount" ? "Enter the discount amount." : "Enter the discount percentage."}>
              <Input name="discountValue" type="number" min={0} step="0.01" value={discountValue || ""} onChange={(e) => setDiscountValue(Number(e.target.value) || 0)} />
            </Field>
          </div>
          <Field label="Amount paid" hint="Leave 0 for credit (payable).">
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
              {pending ? "Saving…" : "Record purchase"}
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
