import { useState } from "react";
import { Modal } from "./ui/modal";
import { Button } from "./ui/button";
import { Field, Input } from "./ui/input";
import { useMutation } from "@/lib/api";
import { money } from "@/lib/utils";

export function RecordPaymentButton({
  onSubmit,
  due,
  currency,
  label = "Record payment",
  variant = "outline",
  onDone,
}: {
  onSubmit: (amount: number) => Promise<unknown>;
  due: number;
  currency: string;
  label?: string;
  variant?: "outline" | "primary" | "ghost";
  onDone?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [amount, setAmount] = useState<number>(due);
  const { run, pending, error } = useMutation();

  function openDialog() {
    setAmount(due);
    setOpen(true);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    await run(
      () => onSubmit(amount),
      () => {
        setOpen(false);
        onDone?.();
      },
    );
  }

  return (
    <>
      <Button variant={variant} size="sm" onClick={openDialog}>
        {label}
      </Button>
      <Modal open={open} onClose={() => setOpen(false)} title="Record payment" className="max-w-md">
        <form onSubmit={submit} className="flex flex-col gap-4">
          <p className="text-sm text-muted-foreground">
            Outstanding: <span className="font-medium text-foreground">{money(due, currency)}</span>
          </p>
          <Field label="Amount">
            <Input
              type="number"
              min={0}
              step="0.01"
              value={amount || ""}
              onChange={(e) => setAmount(Number(e.target.value) || 0)}
              autoFocus
            />
          </Field>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={pending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={pending}>
              {pending ? "Saving…" : "Save payment"}
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
