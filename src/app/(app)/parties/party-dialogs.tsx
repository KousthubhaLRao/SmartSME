"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Icon } from "@/components/icons";
import { createPartyAction, updatePartyAction } from "./actions";

interface PartyLike {
  id: string;
  type: string;
  name: string;
  phone: string | null;
  email: string | null;
  gstNumber: string | null;
  address: string | null;
}

export function PartyDialog({ party, defaultType }: { party?: PartyLike; defaultType?: string }) {
  const editing = Boolean(party);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [phoneError, setPhoneError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const router = useRouter();

  function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const phone = String(fd.get("phone") ?? "");
    if (phone && !/^\+?[0-9]+$/.test(phone)) {
      setPhoneError("Phone number can only contain digits and an optional leading +");
      return;
    }
    setError(null);
    setPhoneError(null);
    start(async () => {
      const res = editing ? await updatePartyAction(party!.id, fd) : await createPartyAction(fd);
      if (res.error) setError(res.error);
      else {
        setOpen(false);
        router.refresh();
      }
    });
  }

  function handlePhoneChange(e: React.ChangeEvent<HTMLInputElement>) {
    const value = e.target.value;
    if (value && !/^\+?[0-9]*$/.test(value)) {
      setPhoneError("Phone number can only contain digits and an optional leading +");
    } else {
      setPhoneError(null);
    }
  }

  return (
    <>
      {editing ? (
        <button
          onClick={() => setOpen(true)}
          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
          aria-label="Edit party"
        >
          <Icon name="edit" size={16} />
        </button>
      ) : (
        <Button onClick={() => setOpen(true)}>
          <Icon name="plus" size={16} /> New party
        </Button>
      )}
      <Modal open={open} onClose={() => setOpen(false)} title={editing ? "Edit party" : "New party"}>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3">
            <Field label="Type">
              <Select name="type" defaultValue={party?.type ?? defaultType ?? "customer"}>
                <option value="customer">Customer</option>
                <option value="supplier">Supplier</option>
              </Select>
            </Field>
            <Field label="Name">
              <Input name="name" defaultValue={party?.name} placeholder="Kumar Traders" required />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Phone">
              <Input
                name="phone"
                defaultValue={party?.phone ?? ""}
                placeholder="+91 …"
                inputMode="numeric"
                onChange={handlePhoneChange}
                pattern="^\\+?[0-9]+$"
              />
              {phoneError && <p className="mt-1 text-sm text-destructive">{phoneError}</p>}
            </Field>
            <Field label="Email">
              <Input name="email" type="email" defaultValue={party?.email ?? ""} placeholder="name@business.com" />
            </Field>
          </div>
          <Field label="GSTIN">
            <Input name="gstNumber" defaultValue={party?.gstNumber ?? ""} placeholder="29ABCDE1234F1Z5" />
          </Field>
          <Field label="Address">
            <Textarea name="address" defaultValue={party?.address ?? ""} placeholder="Optional" />
          </Field>
          {!editing && (
            <Field label="Opening balance ₹" hint="Amount they owe you (customer) or you owe them (supplier).">
              <Input name="openingBalance" type="number" step="0.01" defaultValue={0} />
            </Field>
          )}
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setOpen(false)} disabled={pending}>
              Cancel
            </Button>
            <Button type="submit" disabled={pending}>
              {pending ? "Saving…" : editing ? "Save changes" : "Add party"}
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
