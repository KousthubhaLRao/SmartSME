"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Icon } from "@/components/icons";
import { COUNTRIES, flagEmoji, splitPhone } from "@/lib/countries";
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
  // Phone is split into a country (ISO, drives the dial code) + local number.
  const [phone, setPhone] = useState(() => splitPhone(party?.phone));
  const [pending, start] = useTransition();
  const router = useRouter();

  const dialCode = COUNTRIES.find((c) => c.iso === phone.iso)?.dial ?? "";
  const localNumber = phone.number.replace(/[^0-9]/g, "");
  const combinedPhone = localNumber ? `${dialCode} ${localNumber}` : "";

  function openDialog() {
    // Reset to the party's stored value each time it opens (the "New party"
    // dialog is a single shared instance).
    setPhone(splitPhone(party?.phone));
    setError(null);
    setPhoneError(null);
    setOpen(true);
  }

  function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (phone.number && !/^[0-9\s-]*$/.test(phone.number)) {
      setPhoneError("Phone number can only contain digits.");
      return;
    }
    const fd = new FormData(e.currentTarget);
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

  function handleNumberChange(e: React.ChangeEvent<HTMLInputElement>) {
    const value = e.target.value;
    setPhone((p) => ({ ...p, number: value }));
    setPhoneError(value && !/^[0-9\s-]*$/.test(value) ? "Phone number can only contain digits." : null);
  }

  return (
    <>
      {editing ? (
        <button
          onClick={openDialog}
          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
          aria-label="Edit party"
        >
          <Icon name="edit" size={16} />
        </button>
      ) : (
        <Button onClick={openDialog}>
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
          <Field label="Phone">
            <div className="grid grid-cols-[6.5rem_minmax(0,1fr)] gap-2">
              <Select
                aria-label="Country code"
                className="min-w-0"
                value={phone.iso}
                onChange={(e) => setPhone((p) => ({ ...p, iso: e.target.value }))}
              >
                {COUNTRIES.map((c) => (
                  <option key={c.iso} value={c.iso}>
                    {flagEmoji(c.iso)} {c.dial} {c.name}
                  </option>
                ))}
              </Select>
              <Input
                aria-label="Phone number"
                className="min-w-0"
                placeholder="98765 43210"
                inputMode="tel"
                value={phone.number}
                onChange={handleNumberChange}
              />
            </div>
            {/* The two fields combine into the single stored phone value. */}
            <input type="hidden" name="phone" value={combinedPhone} />
            {phoneError && <p className="mt-1 text-sm text-destructive">{phoneError}</p>}
          </Field>
          <Field label="Email">
            <Input name="email" type="email" defaultValue={party?.email ?? ""} placeholder="name@business.com" />
          </Field>
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
