import { and, eq } from "drizzle-orm";
import { db } from "@/db";
import * as s from "@/db/schema";
import { publish } from "@/lib/events/publish";
import { drainQueue } from "@/worker/loop";
import { round2 } from "@/lib/utils";

export interface CreateExpenseInput {
  category: string;
  description: string;
  amount: number;
  date?: Date;
  source?: string;
}

export async function createExpense(businessId: string, input: CreateExpenseInput) {
  if (!input.description.trim()) throw new Error("Description is required.");
  if (!(input.amount > 0)) throw new Error("Amount must be greater than zero.");

  const expense = await db.transaction(async (tx) => {
    const [row] = await tx
      .insert(s.expenses)
      .values({
        businessId,
        category: input.category.trim() || "General",
        description: input.description.trim(),
        amount: round2(input.amount),
        date: input.date ?? new Date(),
      })
      .returning();

    await publish(tx, businessId, "EXPENSE_ADDED", { expenseId: row.id });
    return row;
  });

  await drainQueue();
  return expense;
}

export async function deleteExpense(businessId: string, expenseId: string) {
  await db
    .delete(s.expenses)
    .where(and(eq(s.expenses.id, expenseId), eq(s.expenses.businessId, businessId)));
}
