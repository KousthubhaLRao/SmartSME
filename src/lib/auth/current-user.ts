import { cache } from "react";
import { redirect } from "next/navigation";
import { eq } from "drizzle-orm";
import { db, ensureReady } from "@/db";
import * as s from "@/db/schema";
import { getSessionUserId } from "./session";

export interface AuthContext {
  user: s.User;
  business: s.Business;
}

// Deduped per request via React cache.
export const getCurrentUser = cache(async (): Promise<AuthContext | null> => {
  // Guarantees the DB connection is initialized before any query — runs on
  // every page and server action (both call requireUser), so it doesn't rely
  // on instrumentation timing (important on serverless / Vercel).
  await ensureReady();
  const userId = await getSessionUserId();
  if (!userId) return null;
  const [user] = await db.select().from(s.users).where(eq(s.users.id, userId));
  if (!user) return null;
  const [business] = await db
    .select()
    .from(s.businesses)
    .where(eq(s.businesses.id, user.businessId));
  if (!business) return null;
  return { user, business };
});

// Use in authenticated pages/actions — redirects to sign-in when absent.
export async function requireUser(): Promise<AuthContext> {
  const ctx = await getCurrentUser();
  if (!ctx) redirect("/sign-in");
  return ctx;
}
