import { Link, useParams } from "react-router-dom";
import { api, useApi } from "@/lib/api";
import { PageState } from "@/components/ui/misc";
import { Card } from "@/components/ui/card";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { PaymentBadge, SourceBadge } from "@/components/Status";
import { Icon } from "@/components/Icon";
import { PrintButton } from "@/components/PrintButton";
import { RecordPaymentButton } from "@/components/RecordPaymentButton";
import { ConfirmButton } from "@/components/ConfirmButton";
import { formatDate, money } from "@/lib/utils";

interface Detail {
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
  business: { name: string; address: string | null; gstNumber: string | null; currency: string };
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className="tabular-nums">{value}</span>
    </div>
  );
}

export function SaleInvoice() {
  const { id } = useParams<{ id: string }>();
  const { data: sale, loading, error, reload } = useApi<Detail>(id ? `/sales/${id}` : null);
  if (!sale) return <PageState loading={loading} error={error} />;

  const cur = sale.business.currency;
  const cancelled = sale.status === "cancelled";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
        <Link
          to="/sales"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <Icon name="chevronRight" size={16} className="rotate-180" /> Back to sales
        </Link>
        <div className="flex items-center gap-2">
          <PrintButton label="Print invoice" />
          {!cancelled && sale.due > 0 && (
            <RecordPaymentButton
              due={sale.due}
              currency={cur}
              variant="primary"
              onSubmit={(amount) => api.post(`/sales/${sale.id}/payment`, { amount })}
              onDone={reload}
            />
          )}
          {!cancelled && (
            <ConfirmButton
              action={() => api.post(`/sales/${sale.id}/cancel`)}
              title="Cancel sale?"
              message={`This reverses inventory and the receivable for ${sale.invoiceNumber}.`}
              confirmLabel="Cancel sale"
              danger
              onDone={reload}
              className="rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:text-destructive"
            >
              Cancel sale
            </ConfirmButton>
          )}
        </div>
      </div>

      <Card className="p-6 sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-border pb-6">
          <div>
            <h1 className="text-xl font-semibold">{sale.business.name}</h1>
            {sale.business.address && (
              <p className="mt-1 max-w-xs text-sm text-muted-foreground">{sale.business.address}</p>
            )}
            {sale.business.gstNumber && (
              <p className="text-sm text-muted-foreground">GSTIN: {sale.business.gstNumber}</p>
            )}
          </div>
          <div className="text-right">
            <div className="text-lg font-semibold">Invoice</div>
            <div className="text-sm text-muted-foreground">{sale.invoiceNumber}</div>
            <div className="mt-1 text-sm text-muted-foreground">{formatDate(sale.date)}</div>
            <div className="mt-2 flex items-center justify-end gap-2">
              <SourceBadge source={sale.source} />
              {cancelled ? (
                <Badge tone="outline">Cancelled</Badge>
              ) : (
                <PaymentBadge status={sale.paymentStatus} />
              )}
            </div>
          </div>
        </div>

        <div className="grid gap-6 py-6 sm:grid-cols-2">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Bill to
            </div>
            <div className="mt-1 font-medium">{sale.party?.name ?? "Walk-in customer"}</div>
            {sale.party?.phone && (
              <div className="text-sm text-muted-foreground">{sale.party.phone}</div>
            )}
            {sale.party?.gstNumber && (
              <div className="text-sm text-muted-foreground">GSTIN: {sale.party.gstNumber}</div>
            )}
          </div>
        </div>

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
            {sale.items.map((it) => (
              <TR key={it.id} className="hover:bg-transparent">
                <TD>{it.description}</TD>
                <TD className="text-right tabular-nums">{it.quantity}</TD>
                <TD className="text-right tabular-nums">{money(it.unitPrice, cur)}</TD>
                <TD className="text-right tabular-nums">{money(it.lineTotal, cur)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>

        <div className="mt-6 flex justify-end">
          <div className="w-full max-w-xs space-y-1.5 text-sm">
            <Row label="Subtotal" value={money(sale.subtotal, cur)} />
            {sale.discountAmount > 0 && (
              <div className="flex justify-between text-success">
                <span>
                  Discount{sale.discountType === "percentage" ? ` (${sale.discountValue}%)` : ""}
                </span>
                <span className="tabular-nums">- {money(sale.discountAmount, cur)}</span>
              </div>
            )}
            <Row label="Tax" value={money(sale.tax, cur)} />
            <div className="flex justify-between border-t border-border pt-2 text-base font-semibold">
              <span>Total</span>
              <span className="tabular-nums">{money(sale.total, cur)}</span>
            </div>
            <Row label="Paid" value={money(sale.amountPaid, cur)} />
            <div className="flex justify-between font-medium text-warning">
              <span>Balance due</span>
              <span className="tabular-nums">{money(cancelled ? 0 : sale.due, cur)}</span>
            </div>
          </div>
        </div>

        {sale.notes && (
          <p className="mt-6 border-t border-border pt-4 text-sm text-muted-foreground">
            <span className="font-medium text-foreground">Notes: </span>
            {sale.notes}
          </p>
        )}
      </Card>
    </div>
  );
}
