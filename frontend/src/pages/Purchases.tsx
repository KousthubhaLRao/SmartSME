import { useState } from "react";
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

interface PurchaseRow {
  id: string;
  referenceNumber: string;
  date: string;
  partyName: string | null;
  source: string;
  status: string;
  total: number;
  amountPaid: number;
  due: number;
  paymentStatus: string;
}

interface PurchasesData {
  rows: PurchaseRow[];
  stats: { totalPurchases: number; payable: number; count: number };
  products: EditorProduct[];
  suppliers: { id: string; name: string }[];
  taxRate: number;
  currency: string;
}

interface PurchaseDetail {
  id: string;
  referenceNumber: string;
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

export function Purchases() {
  const { data, loading, error, reload } = useApi<PurchasesData>("/purchases");
  const [openId, setOpenId] = useState<string | null>(null);
  const [detail, setDetail] = useState<PurchaseDetail | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [newOpen, setNewOpen] = useState(false);

  function openDetail(id: string) {
    setOpenId(id);
    setDetail(null);
    setDetailError(null);
    api
      .get<PurchaseDetail>(`/purchases/${id}`)
      .then(setDetail)
      .catch((e) => setDetailError(e instanceof Error ? e.message : "Could not load that bill."));
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
      <PageHeader title="Purchases" description="Supplier bills and purchase orders.">
        <Can do={PERMISSIONS.txnWrite}>
          <Button onClick={() => setNewOpen(true)}>
            <Icon name="plus" size={16} /> New purchase
          </Button>
        </Can>
      </PageHeader>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Total purchases"
          value={money(data.stats.totalPurchases, cur)}
          icon={<Icon name="purchases" />}
          tone="primary"
        />
        <StatCard
          label="Payable"
          value={money(data.stats.payable, cur)}
          icon={<Icon name="wallet" />}
          tone="warning"
        />
        <StatCard
          label="Bills"
          value={data.stats.count}
          icon={<Icon name="reports" />}
          tone="info"
        />
      </div>

      <Card>
        {data.rows.length === 0 ? (
          <div className="p-6">
            <EmptyState
              icon={<Icon name="purchases" />}
              title="No purchases yet"
              description="Record supplier bills to receive stock and track payables."
            />
          </div>
        ) : (
          <Table>
            <THead>
              <TR className="hover:bg-transparent">
                <TH>Reference</TH>
                <TH>Supplier</TH>
                <TH>Source</TH>
                <TH className="text-right">Total</TH>
                <TH className="text-right">Due</TH>
                <TH>Status</TH>
                <TH className="text-right">Actions</TH>
              </TR>
            </THead>
            <TBody>
              {data.rows.map((p) => {
                const cancelled = p.status === "cancelled";
                return (
                  <TR key={p.id} onClick={() => openDetail(p.id)} className="cursor-pointer">
                    <TD>
                      <div className="font-medium">{p.referenceNumber}</div>
                      <div className="text-xs text-muted-foreground">{formatDate(p.date)}</div>
                    </TD>
                    <TD>{p.partyName ?? <span className="text-muted-foreground">-</span>}</TD>
                    <TD>
                      <SourceBadge source={p.source} />
                    </TD>
                    <TD className="text-right tabular-nums">{money(p.total, cur)}</TD>
                    <TD className="text-right tabular-nums">
                      {cancelled ? "-" : money(p.due, cur)}
                    </TD>
                    <TD>
                      {cancelled ? (
                        <Badge tone="outline">Cancelled</Badge>
                      ) : (
                        <PaymentBadge status={p.paymentStatus} />
                      )}
                    </TD>
                    <TD>
                      <div
                        className="flex items-center justify-end gap-2"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {!cancelled && p.due > 0 && (
                          <RecordPaymentButton
                            due={p.due}
                            currency={cur}
                            label="Pay"
                            onSubmit={(amount) =>
                              api.post(`/purchases/${p.id}/payment`, { amount })
                            }
                            onDone={reload}
                          />
                        )}
                        {!cancelled && (
                          <ConfirmButton
                            needs={PERMISSIONS.dataManage}
                            action={() => api.post(`/purchases/${p.id}/cancel`)}
                            title="Cancel purchase?"
                            message={`This removes received stock and reverses the payable for ${p.referenceNumber}.`}
                            confirmLabel="Cancel purchase"
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

      <Modal
        open={openId !== null}
        onClose={closeDetail}
        title={openRow ? `Bill ${openRow.referenceNumber}` : "Purchase"}
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
                label="Change bill date"
                onSave={(d) => api.patch(`/purchases/${detail.id}/date`, { date: d })}
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
                Supplier
              </div>
              <div className="mt-1 font-medium">{detail.party?.name ?? "Unlinked supplier"}</div>
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

            {detail.status !== "cancelled" && detail.due > 0 && (
              <div className="flex items-center justify-end gap-2 border-t border-border pt-4">
                <RecordPaymentButton
                  due={detail.due}
                  currency={cur}
                  label="Pay"
                  variant="primary"
                  onSubmit={(amount) => api.post(`/purchases/${detail.id}/payment`, { amount })}
                  onDone={() => {
                    reload();
                    openDetail(detail.id);
                  }}
                />
              </div>
            )}
          </div>
        )}
      </Modal>

      <NewPurchaseDialog
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

function NewPurchaseDialog({
  open,
  onClose,
  data,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  data: PurchasesData;
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
        api.post("/purchases", {
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
      title="New purchase"
      description="Received stock is added to inventory automatically."
    >
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Field label="Supplier">
          <Select value={partyId} onChange={(e) => setPartyId(e.target.value)}>
            <option value="">None</option>
            {data.suppliers.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </Select>
        </Field>

        <LineItemsEditor
          products={data.products}
          priceField="purchasePrice"
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

        <Field label="Date" hint="Defaults to today. Back-date it if the bill is older.">
          <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </Field>
        <Field label="Amount paid" hint="Leave 0 for credit (payable).">
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
            {pending ? "Creating…" : "Create purchase"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
