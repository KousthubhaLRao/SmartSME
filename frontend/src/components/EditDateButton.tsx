import { useState } from "react";
import { Modal } from "./ui/modal";
import { Button } from "./ui/button";
import { Field, Input } from "./ui/input";
import { Icon } from "./Icon";
import { useMutation } from "@/lib/api";
import { useCan, type Permission } from "@/lib/session";
import { formatDate, toDateInputValue } from "@/lib/utils";

/**
 * Shows a transaction's business date and lets it be corrected, for entries
 * that were logged late. The date itself is the trigger.
 */
export function EditDateButton({
  date,
  onSave,
  label = "Change date",
  onDone,
  needs,
}: {
  date: string;
  onSave: (isoDate: string) => Promise<unknown>;
  label?: string;
  onDone?: () => void;
  /** Hide the control when the session may not amend documents. */
  needs?: Permission;
}) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(() => toDateInputValue(date));
  const { run, pending, error } = useMutation();
  const can = useCan();
  // After the hooks: an early return above them would break the hook order.
  const allowed = !needs || can(needs);

  function openDialog() {
    setValue(toDateInputValue(date));
    setOpen(true);
  }

  async function save() {
    await run(
      () => onSave(value),
      () => {
        setOpen(false);
        onDone?.();
      },
    );
  }

  if (!allowed) return null;

  return (
    <>
      <button
        type="button"
        title={label}
        onClick={openDialog}
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
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={pending}
            >
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
