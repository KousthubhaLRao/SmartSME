import { useState } from "react";
import { api, useApi, useMutation } from "@/lib/api";
import { PageHeader, PageState, StatCard, SectionCard } from "@/components/ui/misc";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/input";
import { BarList } from "@/components/ui/bar-list";
import { Icon } from "@/components/Icon";
import { RevenueChart } from "@/components/RevenueChart";
import { money } from "@/lib/utils";

interface Overview {
  totals: {
    sales: number;
    purchases: number;
    expenses: number;
    grossProfit: number;
    receivable: number;
    payable: number;
  };
  topProducts: { label: string; value: number; display: string }[];
  topCustomers: { label: string; value: number; display: string }[];
  expenseByCategory: { label: string; value: number; display: string }[];
  currency: string;
}

const TYPES = [
  { value: "consolidated", label: "Everything (consolidated)" },
  { value: "sales", label: "Sales" },
  { value: "purchases", label: "Purchases" },
  { value: "expenses", label: "Expenses" },
];

const PERIODS = [
  { value: "today", label: "Today" },
  { value: "week", label: "Last 7 days" },
  { value: "month", label: "This month" },
  { value: "last_month", label: "Last month" },
  { value: "quarter", label: "Last 3 months" },
  { value: "half_year", label: "Last 6 months" },
  { value: "year", label: "This year" },
  { value: "last_12_months", label: "Last 12 months" },
  { value: "custom", label: "Custom range" },
];

function Line({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className={tone ?? ""}>{value}</span>
    </div>
  );
}

export function Reports() {
  const { data, loading, error } = useApi<Overview>("/reports/overview");
  if (!data) return <PageState loading={loading} error={error} />;

  const cur = data.currency;
  const o = data.totals;
  const netCash = o.sales - o.purchases - o.expenses;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Reports"
        description="Sales, purchases, expenses, and profit at a glance."
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Revenue"
          value={money(o.sales, cur)}
          icon={<Icon name="trendingUp" />}
          tone="success"
        />
        <StatCard
          label="Purchases"
          value={money(o.purchases, cur)}
          icon={<Icon name="purchases" />}
          tone="info"
        />
        <StatCard
          label="Expenses"
          value={money(o.expenses, cur)}
          icon={<Icon name="expenses" />}
          tone="warning"
        />
        <StatCard
          label="Gross profit"
          value={money(o.grossProfit, cur)}
          sub="Revenue minus cost of goods sold"
          icon={<Icon name="wallet" />}
          tone={o.grossProfit >= 0 ? "primary" : "destructive"}
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
          <RevenueChart currency={cur} initialDays={30} />
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <SectionCard title="Top products" description="By revenue">
          <div className="p-5">
            <BarList
              items={data.topProducts}
              colorVar="--chart-1"
              emptyLabel="No sales recorded yet."
            />
          </div>
        </SectionCard>
        <SectionCard title="Top customers" description="By total billed">
          <div className="p-5">
            <BarList
              items={data.topCustomers}
              colorVar="--chart-2"
              emptyLabel="No customer sales yet."
            />
          </div>
        </SectionCard>
        <SectionCard title="Expenses by category">
          <div className="p-5">
            <BarList
              items={data.expenseByCategory}
              colorVar="--chart-3"
              emptyLabel="No expenses yet."
            />
          </div>
        </SectionCard>
        <SectionCard title="Cash flow summary">
          <div className="space-y-2 p-5 text-sm">
            <Line label="Money in (sales)" value={money(o.sales, cur)} tone="text-success" />
            <Line
              label="Money out (purchases)"
              value={money(-o.purchases, cur)}
              tone="text-muted-foreground"
            />
            <Line
              label="Money out (expenses)"
              value={money(-o.expenses, cur)}
              tone="text-muted-foreground"
            />
            <div className="flex items-center justify-between border-t border-border pt-2 font-semibold">
              <span>Net cash</span>
              <span className={netCash >= 0 ? "text-success" : "text-destructive"}>
                {money(netCash, cur)}
              </span>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-3 border-t border-border pt-3">
              <div>
                <div className="text-xs text-muted-foreground">Receivable</div>
                <div className="font-medium">{money(o.receivable, cur)}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Payable</div>
                <div className="font-medium">{money(o.payable, cur)}</div>
              </div>
            </div>
          </div>
        </SectionCard>
      </div>
    </div>
  );
}

function ReportDownload() {
  const [type, setType] = useState("consolidated");
  const [preset, setPreset] = useState("month");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const { run, pending, error } = useMutation();

  function query(fmt: "pdf" | "csv") {
    const p = new URLSearchParams({ type, preset, fmt });
    if (preset === "custom") {
      if (from) p.set("from", from);
      if (to) p.set("to", to);
    }
    return `/reports/download?${p.toString()}`;
  }

  async function download(fmt: "pdf" | "csv") {
    setNote(null);
    await run(async () => {
      const name = await api.download(query(fmt));
      setNote(`Downloaded ${name}`);
    });
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Report">
          <Select value={type} onChange={(e) => setType(e.target.value)}>
            {TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Period">
          <Select value={preset} onChange={(e) => setPreset(e.target.value)}>
            {PERIODS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      {preset === "custom" && (
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="From">
            <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          </Field>
          <Field label="To">
            <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
          </Field>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={() => download("pdf")} disabled={pending}>
          <Icon name="reports" size={16} /> {pending ? "Preparing…" : "Download PDF"}
        </Button>
        <Button variant="outline" onClick={() => download("csv")} disabled={pending}>
          Download CSV
        </Button>
      </div>

      {note && <p className="text-sm text-muted-foreground">{note}</p>}
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
