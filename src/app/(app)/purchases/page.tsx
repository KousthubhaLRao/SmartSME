import { and, desc, eq } from "drizzle-orm";
import { db } from "@/db";
import * as sc from "@/db/schema";
import { requireUser } from "@/lib/auth/current-user";
import { PageHeader, StatCard, EmptyState } from "@/components/ui/misc";
import { Card } from "@/components/ui/card";
import { Icon } from "@/components/icons";
import { money, round2 } from "@/lib/utils";
import { NewPurchaseDialog } from "./new-purchase-dialog";
import { PurchasesTable, type PurchaseListRow } from "./purchases-table";

export default async function PurchasesPage() {
  const { business } = await requireUser();
  const cur = business.currency;

  const rows = await db
    .select({ purchase: sc.purchases, partyName: sc.parties.name })
    .from(sc.purchases)
    .leftJoin(sc.parties, eq(sc.purchases.partyId, sc.parties.id))
    .where(eq(sc.purchases.businessId, business.id))
    .orderBy(desc(sc.purchases.date));

  const products = await db
    .select({
      id: sc.products.id,
      name: sc.products.name,
      unit: sc.products.unit,
      sellingPrice: sc.products.sellingPrice,
      purchasePrice: sc.products.purchasePrice,
    })
    .from(sc.products)
    .where(eq(sc.products.businessId, business.id))
    .orderBy(sc.products.name);

  const suppliers = await db
    .select({ id: sc.parties.id, name: sc.parties.name })
    .from(sc.parties)
    .where(and(eq(sc.parties.businessId, business.id), eq(sc.parties.type, "supplier")))
    .orderBy(sc.parties.name);

  const active = rows.filter((r) => r.purchase.status !== "cancelled");
  const totalPurchases = round2(active.reduce((a, r) => a + r.purchase.total, 0));
  const payable = round2(active.reduce((a, r) => a + (r.purchase.total - r.purchase.amountPaid), 0));

  const tableRows: PurchaseListRow[] = rows.map(({ purchase, partyName }) => ({
    id: purchase.id,
    referenceNumber: purchase.referenceNumber,
    date: purchase.date,
    partyName: partyName ?? null,
    source: purchase.source,
    status: purchase.status,
    total: purchase.total,
    amountPaid: purchase.amountPaid,
    paymentStatus: purchase.paymentStatus,
  }));

  return (
    <div className="space-y-6">
      <PageHeader title="Purchases" description="Supplier bills and purchase orders.">
        <NewPurchaseDialog parties={suppliers} products={products} currency={cur} taxRate={business.taxRate} />
      </PageHeader>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Total purchases" value={money(totalPurchases, cur)} icon={<Icon name="purchases" />} tone="primary" />
        <StatCard label="Payable" value={money(payable, cur)} icon={<Icon name="wallet" />} tone="warning" />
        <StatCard label="Bills" value={active.length} icon={<Icon name="reports" />} tone="info" />
      </div>

      <Card>
        {rows.length === 0 ? (
          <div className="p-6">
            <EmptyState
              icon={<Icon name="purchases" />}
              title="No purchases yet"
              description="Record supplier bills to receive stock and track payables."
            />
          </div>
        ) : (
          <PurchasesTable rows={tableRows} currency={cur} />
        )}
      </Card>
    </div>
  );
}
