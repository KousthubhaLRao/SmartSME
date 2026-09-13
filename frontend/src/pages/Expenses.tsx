import { useState } from "react";
import { api, useApi, useMutation } from "@/lib/api";
import { PageHeader, PageState, StatCard, EmptyState, SectionCard } from "@/components/ui/misc";
import { Card } from "@/components/ui/card";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Field, Input, Select } from "@/components/ui/input";
import { BarList } from "@/components/ui/bar-list";
import { Icon } from "@/components/Icon";
import { ConfirmButton } from "@/components/ConfirmButton";
import { Can, PERMISSIONS } from "@/lib/session";
import { formatDate, money, toDateInputValue } from "@/lib/utils";

const CATEGORIES = [
  "Rent",
  "Utilities",
  "Salary",
  "Transport",
  "Supplies",
  "Marketing",
  "Maintenance",
  "General",
];

interface ExpenseRow {
  id: string;
  category: string;
  description: string;
  amount: number;
  flagged: string | null;
  date: string;
}

interface ExpensesData {
  rows: ExpenseRow[];
  stats: { total: number; count: number; flagged: number };
  byCategory: { label: string; value: number }[];
  currency: string;
}

export function Expenses() {
  const { data, loading, error, reload } = useApi<ExpensesData>("/expenses");
  const [open, setOpen] = useState(false);

  if (!data) return <PageState loading={loading} error={error} />;
  const cur = data.currency;

  return (
    <div className="space-y-6">
      <PageHeader title="Expenses" description="Operating costs, categorised.">
        <Can do={PERMISSIONS.txnWrite}>
          <Button onClick={() => setOpen(true)}>
            <Icon name="plus" size={16} /> New expense
          </Button>
        </Can>
      </PageHeader>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Total expenses"
          value={money(data.stats.total, cur)}
          icon={<Icon name="expenses" />}
          tone="warning"
        />
        <StatCard
          label="Entries"
          value={data.stats.count}
          icon={<Icon name="reports" />}
          tone="info"
        />
        <StatCard
          label="Flagged"
          value={data.stats.flagged}
          sub="Raised by workflow rules"
          icon={<Icon name="alert" />}
          tone="destructive"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          {data.rows.length === 0 ? (
            <div className="p-6">
              <EmptyState
                icon={<Icon name="expenses" />}
                title="No expenses yet"
                description="Log rent, utilities, salaries and other costs."
              />
            </div>
          ) : (
            <Table>
              <THead>
                <TR className="hover:bg-transparent">
                  <TH>Date</TH>
                  <TH>Category</TH>
                  <TH>Description</TH>
                  <TH className="text-right">Amount</TH>
                  <TH className="text-right">Actions</TH>
                </TR>
              </THead>
              <TBody>
                {data.rows.map((e) => (
                  <TR key={e.id}>
                    <TD className="text-muted-foreground">{formatDate(e.date)}</TD>
                    <TD>
                      <Badge tone="default">{e.category}</Badge>
                    </TD>
                    <TD>
                      <div>{e.description}</div>
                      {e.flagged && <div className="mt-0.5 text-xs text-warning">{e.flagged}</div>}
                    </TD>
                    <TD className="text-right tabular-nums font-medium">{money(e.amount, cur)}</TD>
                    <TD>
                      <div className="flex justify-end">
                        <ConfirmButton
                          needs={PERMISSIONS.dataManage}
                          action={() => api.del(`/expenses/${e.id}`)}
                          title="Delete expense?"
                          message={`"${e.description}" will be removed.`}
                          confirmLabel="Delete"
                          danger
                          onDone={reload}
                          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-destructive"
                        >
                          <Icon name="trash" size={16} />
                        </ConfirmButton>
                      </div>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </Card>

        <SectionCard title="By category">
          <div className="p-5">
            <BarList
              items={data.byCategory.map((c) => ({ ...c, display: money(c.value, cur) }))}
              colorVar="--chart-3"
              emptyLabel="No expenses yet."
            />
          </div>
        </SectionCard>
      </div>

      <NewExpenseDialog
        open={open}
        onClose={() => setOpen(false)}
        onCreated={() => {
          setOpen(false);
          reload();
        }}
      />
    </div>
  );
}

function NewExpenseDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const { run, pending, error } = useMutation();
  const [category, setCategory] = useState("General");
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState(0);
  const [date, setDate] = useState(toDateInputValue());

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    await run(
      () => api.post("/expenses", { category, description, amount, date }),
      () => {
        setDescription("");
        setAmount(0);
        onCreated();
      },
    );
  }

  return (
    <Modal open={open} onClose={onClose} title="New expense">
      <form onSubmit={submit} className="flex flex-col gap-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Category">
            <Select value={category} onChange={(e) => setCategory(e.target.value)}>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Amount">
            <Input
              type="number"
              min={0}
              step="0.01"
              value={amount || ""}
              onChange={(e) => setAmount(Number(e.target.value) || 0)}
              required
              autoFocus
            />
          </Field>
        </div>
        <Field label="Description">
          <Input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Electricity bill for March"
            required
          />
        </Field>
        <Field label="Date" hint="Defaults to today.">
          <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </Field>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button type="submit" disabled={pending}>
            {pending ? "Saving…" : "Add expense"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
