import { and, desc, eq } from "drizzle-orm";
import { db } from "@/db";
import * as sc from "@/db/schema";
import { requireUser } from "@/lib/auth/current-user";
import { PageHeader, StatCard, EmptyState } from "@/components/ui/misc";
import { Card } from "@/components/ui/card";
import { Icon } from "@/components/icons";
import { money, round2 } from "@/lib/utils";
import { NewSaleDialog } from "./new-sale-dialog";
import { SalesTable, type SaleListRow } from "./sales-table";

export default async function SalesPage() {
  const { business } = await requireUser();
  const cur = business.currency;

  const rows = await db
    .select({ sale: sc.sales, partyName: sc.parties.name })
    .from(sc.sales)
    .leftJoin(sc.parties, eq(sc.sales.partyId, sc.parties.id))
    .where(eq(sc.sales.businessId, business.id))
    .orderBy(desc(sc.sales.date));

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

  const customers = await db
    .select({ id: sc.parties.id, name: sc.parties.name })
    .from(sc.parties)
    .where(and(eq(sc.parties.businessId, business.id), eq(sc.parties.type, "customer")))
    .orderBy(sc.parties.name);

  const active = rows.filter((r) => r.sale.status !== "cancelled");
  const totalSales = round2(active.reduce((a, r) => a + r.sale.total, 0));
  const receivable = round2(active.reduce((a, r) => a + (r.sale.total - r.sale.amountPaid), 0));

  const tableRows: SaleListRow[] = rows.map(({ sale, partyName }) => ({
    id: sale.id,
    invoiceNumber: sale.invoiceNumber,
    date: sale.date,
    partyName: partyName ?? null,
    source: sale.source,
    status: sale.status,
    total: sale.total,
    amountPaid: sale.amountPaid,
    paymentStatus: sale.paymentStatus,
  }));

  return (
    <div className="space-y-6">
      <PageHeader title="Sales" description="Invoices and customer orders.">
        <NewSaleDialog parties={customers} products={products} currency={cur} taxRate={business.taxRate} />
      </PageHeader>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Total sales" value={money(totalSales, cur)} icon={<Icon name="sales" />} tone="primary" />
        <StatCard label="Receivable" value={money(receivable, cur)} icon={<Icon name="wallet" />} tone="warning" />
        <StatCard label="Invoices" value={active.length} icon={<Icon name="reports" />} tone="info" />
      </div>

      <Card>
        {rows.length === 0 ? (
          <div className="p-6">
            <EmptyState
              icon={<Icon name="sales" />}
              title="No sales yet"
              description="Create your first invoice, or use the Smart Input engine to log a sale in plain language."
            />
          </div>
        ) : (
          <SalesTable rows={tableRows} currency={cur} />
        )}
      </Card>
    </div>
  );
}
