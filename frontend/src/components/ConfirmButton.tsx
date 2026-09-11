import { useState } from "react";
import { Modal } from "./ui/modal";
import { Button } from "./ui/button";
import { useMutation } from "@/lib/api";
import { cn } from "@/lib/utils";

export function ConfirmButton({
  action,
  title,
  message,
  confirmLabel = "Confirm",
  children,
  className,
  danger,
  onDone,
}: {
  action: () => Promise<unknown>;
  title: string;
  message: string;
  confirmLabel?: string;
  children: React.ReactNode;
  className?: string;
  danger?: boolean;
  onDone?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const { run, pending, error } = useMutation();

  async function go() {
    const ok = await run(action, () => {
      setOpen(false);
      onDone?.();
    });
    if (!ok) return;
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={cn("inline-flex items-center gap-1.5", className)}
      >
        {children}
      </button>
      <Modal open={open} onClose={() => setOpen(false)} title={title} className="max-w-md">
        <p className="text-sm text-muted-foreground">{message}</p>
        {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="outline" onClick={() => setOpen(false)} disabled={pending}>
            Cancel
          </Button>
          <Button variant={danger ? "destructive" : "primary"} onClick={go} disabled={pending}>
            {pending ? "Working…" : confirmLabel}
          </Button>
        </div>
      </Modal>
    </>
  );
}
