import { and, eq } from "drizzle-orm";
import { db } from "@/db";
import * as s from "@/db/schema";

export interface PartyInput {
  type: "customer" | "supplier";
  name: string;
  phone?: string | null;
  email?: string | null;
  gstNumber?: string | null;
  address?: string | null;
  openingBalance?: number;
}

function normalizePhone(phone?: string | null): string | null {
  if (!phone) return null;
  const cleaned = phone.trim().replace(/[\s-]/g, "");
  if (!cleaned) return null;
  if (!/^\+?[0-9]+$/.test(cleaned)) {
    throw new Error("Phone number can only contain digits and an optional leading +");
  }
  return cleaned;
}

export async function createParty(businessId: string, input: PartyInput) {
  if (!input.name.trim()) throw new Error("Name is required.");
  const openingBalance = Number(input.openingBalance ?? 0);
  const phone = normalizePhone(input.phone);
  if (!Number.isFinite(openingBalance)) throw new Error("Opening balance must be a valid number.");
  const [party] = await db
    .insert(s.parties)
    .values({
      businessId,
      type: input.type === "supplier" ? "supplier" : "customer",
      name: input.name.trim(),
      phone,
      email: input.email || null,
      gstNumber: input.gstNumber || null,
      address: input.address || null,
      balance: openingBalance,
    })
    .returning();
  return party;
}

export async function updateParty(businessId: string, partyId: string, input: PartyInput) {
  if (!input.name.trim()) throw new Error("Name is required.");
  const phone = normalizePhone(input.phone);
  await db
    .update(s.parties)
    .set({
      type: input.type === "supplier" ? "supplier" : "customer",
      name: input.name.trim(),
      phone,
      email: input.email || null,
      gstNumber: input.gstNumber || null,
      address: input.address || null,
    })
    .where(and(eq(s.parties.id, partyId), eq(s.parties.businessId, businessId)));
}

export async function deleteParty(businessId: string, partyId: string) {
  await db
    .delete(s.parties)
    .where(and(eq(s.parties.id, partyId), eq(s.parties.businessId, businessId)));
}
