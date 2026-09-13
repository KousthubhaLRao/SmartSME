import { useState } from "react";
import { Link } from "react-router-dom";
import { api, useApi, useMutation } from "@/lib/api";
import { PageHeader, PageState, StatCard, EmptyState, Skeleton } from "@/components/ui/misc";
import { Card } from "@/components/ui/card";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { PaymentBadge, SourceBadge } from "@/components/Status";
import { Icon } from "@/components/Icon";
import { LineItemsEditor, type EditorProduct, type LineRow } from "@/components/LineItemsEditor";
import { RecordPaymentButton } from "@/components/RecordPaymentButton";
import { ConfirmButton } from "@/components/ConfirmButton";
import { EditDateButton } from "@/components/EditDateButton";
import { Can, PERMISSIONS } from "@/lib/session";
import { formatDate, money, toDateInputValue } from "@/lib/utils";

interface SaleRow {
  id: string;
  invoiceNumber: string;
  date: string;
  partyName: string | null;
  source: string;
  status: string;
  total: number;
  amountPaid: number;
  due: number;
  paymentStatus: string;
}

interface SalesData {
  rows: SaleRow[];
  stats: { totalSales: number; receivable: number; count: number };
  products: EditorProduct[];
  customers: { id: string; name: string }[];
  taxRate: number;
  currency: string;
}

interface SaleDetail {
  id: string;
  invoiceNumber: string;
  date: string;
  status: string;
  source: string;
  subtotal: number;
  discountType: string;
  discountValue: number;
  discountAmount: number;
  tax: number;
  total: number;
  amountPaid: number;
  due: number;
  paymentStatus: string;
  notes: string | null;
  party: { name: string; phone: string | null; gstNumber: string | null } | null;
  items: {
    id: string;
    description: string;
    quantity: number;
    unitPrice: number;
    lineTotal: number;
  }[];
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className="tabular-nums">{value}</span>
    </div>
  );
}

export function Sales() {
  const { data, loading, error, reload } = useApi<SalesData>("/sales");
  const [openId, setOpenId] = useState<string | null>(null);
  const [detail, setDetail] = useState<SaleDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [newOpen, setNewOpen] = useState(false);

  function openDetail(id: string) {
    setOpenId(id);
    setDetail(null);
    setDetailError(null);
    api
      .get<SaleDetail>(`/sales/${id}`)
      .then(setDetail)
      .catch((e) => setDetailError(e instanceof Error ? e.message : "Could not load that sale."));
  }

  function closeDetail() {
    setOpenId(null);
    setDetail(null);
    setDetailError(null);
  }

  if (!data) return <PageState loading={loading} error={error} />;
  const cur = data.currency;
  const openRow = data.rows.find((r) => r.id === openId);

  return (
    <div className="space-y-6">
      <PageHeader title="Sales" description="Invoices and customer orders.">
        <Can do={PERMISSIONS.txnWrite}>
          <Button onClick={() => setNewOpen(true)}>
            <Icon name="plus" size={16} /> New sale
          </Button>
        </Can>
      </PageHeader>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Total sales"
          value={money(data.stats.totalSales, cur)}
          icon={<Icon name="sales" />}
          tone="primary"
        />
        <StatCard
          label="Receivable"
          value={money(data.stats.receivable, cur)}
          icon={<Icon name="wallet" />}
          tone="warning"
        />
        <StatCard
          label="Invoices"
          value={data.stats.count}
          icon={<Icon name="reports" />}
          tone="info"
        />
      </div>

      <Card>
        {data.rows.length === 0 ? (
          <div className="p-6">
            <EmptyState
              icon={<Icon name="sales" />}
              title="No sales yet"
              description="Create your first invoice, or use Smart Input to log a sale in plain language."
            />
          </div>
        ) : (
          <Table>
            <THead>
              <TR className="hover:bg-transparent">
                <TH>Invoice</TH>
                <TH>Customer</TH>
                <TH>Source</TH>
                <TH className="text-right">Total</TH>
                <TH className="text-right">Due</TH>
                <TH>Status</TH>
                <TH className="text-right">Actions</TH>
              </TR>
            </THead>
            <TBody>
              {data.rows.map((sale) => {
                const cancelled = sale.status === "cancelled";
                return (
                  <TR key={sale.id} onClick={() => openDetail(sale.id)} className="cursor-pointer">
                    <TD>
                      <div className="font-medium">{sale.invoiceNumber}</div>
                      <div className="text-xs text-muted-foreground">{formatDate(sale.date)}</div>
                    </TD>
                    <TD>
                      {sale.partyName ?? <span className="text-muted-foreground">Walk-in</span>}
                    </TD>
                    <TD>
                      <SourceBadge source={sale.source} />
                    </TD>
                    <TD className="text-right tabular-nums">{money(sale.total, cur)}</TD>
                    <TD className="text-right tabular-nums">
                      {cancelled ? "-" : money(sale.due, cur)}
                    </TD>
                    <TD>
                      {cancelled ? (
                        <Badge tone="outline">Cancelled</Badge>
                      ) : (
                        <PaymentBadge status={sale.paymentStatus} />
                      )}
                    </TD>
                    <TD>
                      {/* Stop row-click from firing when using the inline actions. */}
                      <div
                        className="flex items-center justify-end gap-2"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {!cancelled && sale.due > 0 && (
                          <RecordPaymentButton
                            due={sale.due}
                            currency={cur}
                            onSubmit={(amount) => api.post(`/sales/${sale.id}/payment`, { amount })}
                            onDone={reload}
                          />
                        )}
                        {!cancelled && (
                          <ConfirmButton
                            needs={PERMISSIONS.dataManage}
                            action={() => api.post(`/sales/${sale.id}/cancel`)}
                            title="Cancel sale?"
                            message={`This will reverse the inventory and receivable for ${sale.invoiceNumber}.`}
                            confirmLabel="Cancel sale"
                            danger
                            onDone={reload}
                            className="text-sm text-muted-foreground hover:text-destructive"
                          >
                            <Icon name="trash" size={16} />
                          </ConfirmButton>
                        )}
                      </div>
                    </TD>
                  </TR>
                );
              })}
            </TBody>
          </Table>
        )}
      </Card>

      {/* Detail modal */}
      <Modal
        open={openId !== null}
        onClose={closeDetail}
        title={openRow ? `Invoice ${openRow.invoiceNumber}` : "Sale"}
        className="max-w-2xl"
      >
        {detailError ? (
          <p className="text-sm text-destructive">{detailError}</p>
        ) : !detail ? (
          <div className="space-y-3">
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-4 w-2/3" />
          </div>
        ) : (
          <div className="space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <EditDateButton
                needs={PERMISSIONS.dataManage}
                date={detail.date}
                label="Change sale date"
                onSave={(d) => api.patch(`/sales/${detail.id}/date`, { date: d })}
                onDone={() => {
                  reload();
                  openDetail(detail.id);
                }}
              />
              <div className="flex items-center gap-2">
                <SourceBadge source={detail.source} />
                {detail.status === "cancelled" ? (
                  <Badge tone="outline">Cancelled</Badge>
                ) : (
                  <PaymentBadge status={detail.paymentStatus} />
                )}
              </div>
            </div>

            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Bill to
              </div>
              <div className="mt-1 font-medium">{detail.party?.name ?? "Walk-in customer"}</div>
              {detail.party?.phone && (
                <div className="text-sm text-muted-foreground">{detail.party.phone}</div>
              )}
              {detail.party?.gstNumber && (
                <div className="text-sm text-muted-foreground">GSTIN: {detail.party.gstNumber}</div>
              )}
            </div>

            <div className="overflow-hidden rounded-lg border border-border">
              <Table>
                <THead>
                  <TR className="hover:bg-transparent">
                    <TH>Item</TH>
                    <TH className="text-right">Qty</TH>
                    <TH className="text-right">Unit price</TH>
                    <TH className="text-right">Total</TH>
                  </TR>
                </THead>
                <TBody>
                  {detail.items.map((it) => (
                    <TR key={it.id} className="hover:bg-transparent">
                      <TD>{it.description}</TD>
                      <TD className="text-right tabular-nums">{it.quantity}</TD>
                      <TD className="text-right tabular-nums">{money(it.unitPrice, cur)}</TD>
                      <TD className="text-right tabular-nums">{money(it.lineTotal, cur)}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </div>

            <div className="flex justify-end">
              <div className="w-full max-w-xs space-y-1.5 text-sm">
                <Row label="Subtotal" value={money(detail.subtotal, cur)} />
                {detail.discountAmount > 0 && (
                  <div className="flex justify-between text-success">
                    <span>
                      Discount
                      {detail.discountType === "percentage" ? ` (${detail.discountValue}%)` : ""}
                    </span>
                    <span className="tabular-nums">- {money(detail.discountAmount, cur)}</span>
                  </div>
                )}
                <Row label="Tax" value={money(detail.tax, cur)} />
                <div className="flex justify-between border-t border-border pt-2 text-base font-semibold">
                  <span>Total</span>
                  <span className="tabular-nums">{money(detail.total, cur)}</span>
                </div>
                <Row label="Paid" value={money(detail.amountPaid, cur)} />
                <div className="flex justify-between font-medium text-warning">
                  <span>Balance due</span>
                  <span className="tabular-nums">{money(detail.due, cur)}</span>
                </div>
              </div>
            </div>

            {detail.notes && (
              <p className="border-t border-border pt-4 text-sm text-muted-foreground">
                <span className="font-medium text-foreground">Notes: </span>
                {detail.notes}
              </p>
            )}

            <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border pt-4">
              <Link
                to={`/sales/${detail.id}`}
                className="inline-flex items-center gap-1 text-sm text-link hover:underline"
              >
                Open full invoice <Icon name="chevronRight" size={15} />
              </Link>
              {detail.status !== "cancelled" && detail.due > 0 && (
                <RecordPaymentButton
                  due={detail.due}
                  currency={cur}
                  variant="primary"
                  onSubmit={(amount) => api.post(`/sales/${detail.id}/payment`, { amount })}
                  onDone={() => {
                    reload();
                    openDetail(detail.id);
                  }}
                />
              )}
            </div>
          </div>
        )}
      </Modal>

      <NewSaleDialog
        open={newOpen}
        onClose={() => setNewOpen(false)}
        data={data}
        onCreated={() => {
          setNewOpen(false);
          reload();
        }}
      />
    </div>
  );
}

function NewSaleDialog({
  open,
  onClose,
  data,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  data: SalesData;
  onCreated: () => void;
}) {
  const { run, pending, error } = useMutation();
  const [partyId, setPartyId] = useState("");
  const [items, setItems] = useState<LineRow[]>([]);
  const [discountType, setDiscountType] = useState<"none" | "amount" | "percentage">("none");
  const [discountValue, setDiscountValue] = useState(0);
  const [amountPaid, setAmountPaid] = useState(0);
  const [notes, setNotes] = useState("");
  const [date, setDate] = useState(toDateInputValue());

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    await run(
      () =>
        api.post("/sales", {
          partyId: partyId || null,
          items: items.filter((i) => i.description.trim() && i.quantity > 0),
          amountPaid,
          discountType,
          discountValue,
          notes: notes || null,
          date,
        }),
      onCreated,
    );
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New sale"
      description="Inventory and balances update automatically via the event bus."
    >
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Field label="Customer">
          <Select value={partyId} onChange={(e) => setPartyId(e.target.value)}>
            <option value="">Walk-in / none</option>
            {data.customers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
        </Field>

        <LineItemsEditor
          products={data.products}
          priceField="sellingPrice"
          taxRate={data.taxRate}
          currency={data.currency}
          discountType={discountType}
          discountValue={discountValue}
          onChange={setItems}
        />

        <div className="grid gap-3 md:grid-cols-2">
          <Field label="Discount type">
            <Select
              value={discountType}
              onChange={(e) => setDiscountType(e.target.value as typeof discountType)}
            >
              <option value="none">No discount</option>
              <option value="amount">Amount</option>
              <option value="percentage">Percentage</option>
            </Select>
          </Field>
          <Field label="Discount value" hint="Enter amount or % depending on the selected type.">
            <Input
              type="number"
              min={0}
              step="0.01"
              value={discountValue || ""}
              onChange={(e) => setDiscountValue(Number(e.target.value) || 0)}
            />
          </Field>
        </div>

        <Field label="Date" hint="Defaults to today. Back-date it if the sale happened earlier.">
          <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </Field>
        <Field label="Amount paid" hint="Leave 0 for a credit sale (unpaid).">
          <Input
            type="number"
            min={0}
            step="0.01"
            value={amountPaid || ""}
            onChange={(e) => setAmountPaid(Number(e.target.value) || 0)}
          />
        </Field>
        <Field label="Notes">
          <Textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Optional"
          />
        </Field>

        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button type="submit" disabled={pending}>
            {pending ? "Creating…" : "Create sale"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
