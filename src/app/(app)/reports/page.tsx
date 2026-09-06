import { requireUser } from "@/lib/auth/current-user";
import { loadOverview, getRevenueSeries } from "@/lib/analytics";
import { PageHeader, StatCard, SectionCard } from "@/components/ui/misc";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { BarList } from "@/components/ui/bar-list";
import { Icon } from "@/components/icons";
import { money } from "@/lib/utils";
import { RevenueChart } from "./revenue-chart";
import { ReportDownload } from "./report-download";

const DEFAULT_RANGE_DAYS = 30;

export default async function ReportsPage() {
  const { business } = await requireUser();
  const cur = business.currency;
  const o = await loadOverview(business.id, 14);
  const revenueSeries = await getRevenueSeries(business.id, DEFAULT_RANGE_DAYS);

  const netCash = o.totals.sales - o.totals.purchases - o.totals.expenses;

  return (
    <div className="space-y-6">
      <PageHeader title="Reports" description="Sales, purchases, expenses, and profit at a glance." />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Revenue" value={money(o.totals.sales, cur)} icon={<Icon name="trendingUp" />} tone="success" />
        <StatCard label="Purchases" value={money(o.totals.purchases, cur)} icon={<Icon name="purchases" />} tone="info" />
        <StatCard label="Expenses" value={money(o.totals.expenses, cur)} icon={<Icon name="expenses" />} tone="warning" />
        <StatCard
          label="Gross profit"
          value={money(o.totals.grossProfit, cur)}
          sub="Revenue − cost of goods sold"
          icon={<Icon name="wallet" />}
          tone={o.totals.grossProfit >= 0 ? "primary" : "destructive"}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Download a report</CardTitle>
          <CardDescription>
            Export sales, purchases, expenses, or everything together for any period.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ReportDownload />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Revenue</CardTitle>
        </CardHeader>
        <CardContent>
          <RevenueChart initialData={revenueSeries} initialDays={DEFAULT_RANGE_DAYS} currency={cur} />
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <SectionCard title="Top products" description="By revenue">
          <div className="p-5">
            <BarList items={o.topProducts} colorVar="--chart-1" emptyLabel="No sales recorded yet." />
          </div>
        </SectionCard>
        <SectionCard title="Top customers" description="By total billed">
          <div className="p-5">
            <BarList items={o.topCustomers} colorVar="--chart-2" emptyLabel="No customer sales yet." />
          </div>
        </SectionCard>
        <SectionCard title="Expenses by category">
          <div className="p-5">
            <BarList items={o.expenseByCategory} colorVar="--chart-3" emptyLabel="No expenses yet." />
          </div>
        </SectionCard>
        <SectionCard title="Cash flow summary">
          <div className="space-y-2 p-5 text-sm">
            <Line label="Money in (sales)" value={money(o.totals.sales, cur)} tone="text-success" />
            <Line label="Money out (purchases)" value={money(-o.totals.purchases, cur)} tone="text-muted-foreground" />
            <Line label="Money out (expenses)" value={money(-o.totals.expenses, cur)} tone="text-muted-foreground" />
            <div className="flex items-center justify-between border-t border-border pt-2 font-semibold">
              <span>Net cash</span>
              <span className={netCash >= 0 ? "text-success" : "text-destructive"}>{money(netCash, cur)}</span>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-3 border-t border-border pt-3">
              <div>
                <div className="text-xs text-muted-foreground">Receivable</div>
                <div className="font-medium">{money(o.totals.receivable, cur)}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Payable</div>
                <div className="font-medium">{money(o.totals.payable, cur)}</div>
              </div>
            </div>
          </div>
        </SectionCard>
      </div>
    </div>
  );
}

function Line({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className={tone ?? ""}>{value}</span>
    </div>
  );
}
