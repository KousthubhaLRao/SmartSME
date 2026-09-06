import Link from "next/link";
import { and, desc, eq, ne } from "drizzle-orm";
import { db } from "@/db";
import * as sc from "@/db/schema";
import { requireUser } from "@/lib/auth/current-user";
import { PageHeader, StatCard, EmptyState } from "@/components/ui/misc";
import { Card } from "@/components/ui/card";
import { Icon } from "@/components/icons";
import { cn, money, round2 } from "@/lib/utils";
import { ConfirmButton } from "@/components/confirm-button";
import { buttonVariants } from "@/components/ui/button";
import { PartyDialog } from "./party-dialogs";
import { PartiesTable, type PartyRow, type OutstandingDoc } from "./parties-table";
import { settleAllPayablesAction, settleAllReceivablesAction } from "./actions";

export default async function PartiesPage({
  searchParams,
}: {
  searchParams: Promise<{ type?: string }>;
}) {
  const { business } = await requireUser();
  const cur = business.currency;
  const { type } = await searchParams;
  const filter = type === "supplier" || type === "customer" ? type : "all";

  const all = await db
    .select()
    .from(sc.parties)
    .where(eq(sc.parties.businessId, business.id))
    .orderBy(sc.parties.name);

  // Outstanding customer invoices and supplier bills, so each party row can be
  // expanded to show exactly what makes up its balance and paid off in bulk.
  const openSales = await db
    .select({
      id: sc.sales.id,
      partyId: sc.sales.partyId,
      ref: sc.sales.invoiceNumber,
      date: sc.sales.date,
      total: sc.sales.total,
      amountPaid: sc.sales.amountPaid,
    })
    .from(sc.sales)
    .where(and(eq(sc.sales.businessId, business.id), ne(sc.sales.status, "cancelled")))
    .orderBy(desc(sc.sales.date));

  const openPurchases = await db
    .select({
      id: sc.purchases.id,
      partyId: sc.purchases.partyId,
      ref: sc.purchases.referenceNumber,
      date: sc.purchases.date,
      total: sc.purchases.total,
      amountPaid: sc.purchases.amountPaid,
    })
    .from(sc.purchases)
    .where(and(eq(sc.purchases.businessId, business.id), ne(sc.purchases.status, "cancelled")))
    .orderBy(desc(sc.purchases.date));

  const outstandingByParty = new Map<string, OutstandingDoc[]>();
  const pushDoc = (r: { id: string; partyId: string | null; ref: string; date: Date; total: number; amountPaid: number }) => {
    const due = round2(r.total - r.amountPaid);
    if (!r.partyId || due <= 0.001) return;
    const list = outstandingByParty.get(r.partyId) ?? [];
    list.push({ id: r.id, ref: r.ref, date: r.date, total: r.total, due });
    outstandingByParty.set(r.partyId, list);
  };
  openSales.forEach(pushDoc);
  openPurchases.forEach(pushDoc);

  const rows: PartyRow[] = all.map((p) => ({
    id: p.id,
    type: p.type,
    name: p.name,
    phone: p.phone,
    email: p.email,
    gstNumber: p.gstNumber,
    address: p.address,
    balance: p.balance,
    outstanding: outstandingByParty.get(p.id) ?? [],
  }));

  const visible = filter === "all" ? rows : rows.filter((p) => p.type === filter);

  const receivable = round2(
    rows.filter((p) => p.type === "customer" && p.balance > 0).reduce((a, p) => a + p.balance, 0),
  );
  const payable = round2(
    rows.filter((p) => p.type === "supplier" && p.balance > 0).reduce((a, p) => a + p.balance, 0),
  );

  const tabs = [
    { key: "all", label: `All (${rows.length})`, href: "/parties" },
    { key: "customer", label: `Customers (${rows.filter((p) => p.type === "customer").length})`, href: "/parties?type=customer" },
    { key: "supplier", label: `Suppliers (${rows.filter((p) => p.type === "supplier").length})`, href: "/parties?type=supplier" },
  ];

  const showReceivablesAction = (filter === "all" || filter === "customer") && receivable > 0;
  const showPayablesAction = (filter === "all" || filter === "supplier") && payable > 0;

  return (
    <div className="space-y-6">
      <PageHeader title="Parties" description="Customers and suppliers, with outstanding balances.">
        <PartyDialog defaultType={filter === "supplier" ? "supplier" : "customer"} />
      </PageHeader>

      <div className="grid gap-4 sm:grid-cols-2">
        <StatCard label="Total receivable" value={money(receivable, cur)} sub="Owed to you by customers" icon={<Icon name="trendingUp" />} tone="success" />
        <StatCard label="Total payable" value={money(payable, cur)} sub="Owed by you to suppliers" icon={<Icon name="trendingDown" />} tone="warning" />
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex gap-1 rounded-lg border border-border bg-card p-1 text-sm">
          {tabs.map((t) => (
            <Link
              key={t.key}
              href={t.href}
              className={cn(
                "rounded-md px-3 py-1.5 font-medium transition-colors",
                filter === t.key
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {t.label}
            </Link>
          ))}
        </div>

        {(showReceivablesAction || showPayablesAction) && (
          <div className="flex flex-wrap items-center gap-2">
            {showReceivablesAction && (
              <ConfirmButton
                action={settleAllReceivablesAction}
                title="Mark all receivables as paid?"
                message={`Every outstanding customer invoice (${money(receivable, cur)}) will be marked fully paid and balances cleared.`}
                confirmLabel="Mark all as paid"
                className={buttonVariants({ variant: "outline", size: "sm" })}
              >
                <Icon name="check" size={15} /> Receivables paid
              </ConfirmButton>
            )}
            {showPayablesAction && (
              <ConfirmButton
                action={settleAllPayablesAction}
                title="Mark all payables as paid?"
                message={`Every outstanding supplier bill (${money(payable, cur)}) will be marked fully paid and balances cleared.`}
                confirmLabel="Mark all as paid"
                className={buttonVariants({ variant: "outline", size: "sm" })}
              >
                <Icon name="check" size={15} /> Payables paid
              </ConfirmButton>
            )}
          </div>
        )}
      </div>

      <Card>
        {visible.length === 0 ? (
          <div className="p-6">
            <EmptyState
              icon={<Icon name="parties" />}
              title="No parties here"
              description="Add customers and suppliers to track balances and transaction history."
            />
          </div>
        ) : (
          <PartiesTable rows={visible} currency={cur} />
        )}
      </Card>
    </div>
  );
}
