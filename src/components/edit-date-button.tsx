"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { Icon } from "@/components/icons";
import { formatDate, toDateInputValue } from "@/lib/utils";

/**
 * Shows a transaction's business date and lets it be corrected, for entries
 * that were logged late. Renders the date itself as the trigger.
 */
export function EditDateButton({
  action,
  id,
  date,
  label = "Change date",
}: {
  action: (id: string, dateStr: string) => Promise<{ error?: string }>;
  id: string;
  date: Date | string;
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(() => toDateInputValue(date));
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const router = useRouter();

  function save() {
    setError(null);
    start(async () => {
      const res = await action(id, value);
      if (res?.error) setError(res.error);
      else {
        setOpen(false);
        router.refresh();
      }
    });
  }

  return (
    <>
      <button
        type="button"
        title={label}
        onClick={() => {
          setValue(toDateInputValue(date));
          setError(null);
          setOpen(true);
        }}
        className="inline-flex items-center gap-1.5 rounded-md text-sm text-muted-foreground hover:text-foreground"
      >
        {formatDate(date)}
        <Icon name="edit" size={13} />
      </button>

      <Modal open={open} onClose={() => setOpen(false)} title={label} className="max-w-sm">
        <div className="flex flex-col gap-4">
          <Field label="Date" hint="Set the date this actually happened.">
            <Input type="date" value={value} onChange={(e) => setValue(e.target.value)} autoFocus />
          </Field>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setOpen(false)} disabled={pending}>
              Cancel
            </Button>
            <Button type="button" onClick={save} disabled={pending || !value}>
              {pending ? "Saving…" : "Save date"}
            </Button>
          </div>
        </div>
      </Modal>
    </>
  );
}
