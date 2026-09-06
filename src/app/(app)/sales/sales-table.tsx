"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { Modal } from "@/components/ui/modal";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { PaymentBadge, SourceBadge } from "@/components/status";
import { Icon } from "@/components/icons";
import { RecordPaymentButton } from "@/components/record-payment-button";
import { ConfirmButton } from "@/components/confirm-button";
import { Skeleton } from "@/components/ui/misc";
import { EditDateButton } from "@/components/edit-date-button";
import { money, formatDate, round2 } from "@/lib/utils";
import { recordSalePaymentAction, cancelSaleAction, loadSaleDetailAction, updateSaleDateAction, type SaleDetail } from "./actions";

export interface SaleListRow {
  id: string;
  invoiceNumber: string;
  date: Date;
  partyName: string | null;
  source: string;
  status: string;
  total: number;
  amountPaid: number;
  paymentStatus: string;
}

export function SalesTable({ rows, currency }: { rows: SaleListRow[]; currency: string }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const [detail, setDetail] = useState<SaleDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, start] = useTransition();

  function openDetail(id: string) {
    setOpenId(id);
    setDetail(null);
    setError(null);
    start(async () => {
      const res = await loadSaleDetailAction(id);
      if (res.error) setError(res.error);
      else setDetail(res.detail ?? null);
    });
  }

  function close() {
    setOpenId(null);
    setDetail(null);
    setError(null);
  }

  const openRow = rows.find((r) => r.id === openId);

  return (
    <>
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
          {rows.map((sale) => {
            const due = round2(sale.total - sale.amountPaid);
            const cancelled = sale.status === "cancelled";
            return (
              <TR
                key={sale.id}
                onClick={() => openDetail(sale.id)}
                className="cursor-pointer"
              >
                <TD>
                  <div className="font-medium">{sale.invoiceNumber}</div>
                  <div className="text-xs text-muted-foreground">{formatDate(sale.date)}</div>
                </TD>
                <TD>{sale.partyName ?? <span className="text-muted-foreground">Walk-in</span>}</TD>
                <TD>
                  <SourceBadge source={sale.source} />
                </TD>
                <TD className="text-right tabular-nums">{money(sale.total, currency)}</TD>
                <TD className="text-right tabular-nums">{cancelled ? "-" : money(due, currency)}</TD>
                <TD>
                  {cancelled ? <Badge tone="outline">Cancelled</Badge> : <PaymentBadge status={sale.paymentStatus} />}
                </TD>
                <TD>
                  {/* Stop row-click from firing when using the inline actions. */}
                  <div className="flex items-center justify-end gap-2" onClick={(e) => e.stopPropagation()}>
                    {!cancelled && due > 0 && (
                      <RecordPaymentButton
                        action={recordSalePaymentAction}
                        idName="saleId"
                        idValue={sale.id}
                        due={due}
                        currency={currency}
                      />
                    )}
                    {!cancelled && (
                      <ConfirmButton
                        action={cancelSaleAction.bind(null, sale.id)}
                        title="Cancel sale?"
                        message={`This will reverse the inventory and receivable for ${sale.invoiceNumber}.`}
                        confirmLabel="Cancel sale"
                        danger
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

      <Modal
        open={openId !== null}
        onClose={close}
        title={openRow ? `Invoice ${openRow.invoiceNumber}` : "Sale"}
        className="max-w-2xl"
      >
        {error ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : loading || !detail ? (
          <DetailSkeleton />
        ) : (
          <SaleDetailView detail={detail} currency={currency} onDone={close} />
        )}
      </Modal>
    </>
  );
}

function DetailSkeleton() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-5 w-40" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-2/3" />
    </div>
  );
}

function SaleDetailView({
  detail,
  currency,
  onDone,
}: {
  detail: SaleDetail;
  currency: string;
  onDone: () => void;
}) {
  const { sale, party, items } = detail;
  const due = round2(sale.total - sale.amountPaid);
  const cancelled = sale.status === "cancelled";

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <EditDateButton action={updateSaleDateAction} id={sale.id} date={sale.date} label="Change sale date" />
        <div className="flex items-center gap-2">
          <SourceBadge source={sale.source} />
          {cancelled ? <Badge tone="outline">Cancelled</Badge> : <PaymentBadge status={sale.paymentStatus} />}
        </div>
      </div>

      <div>
        <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Bill to</div>
        <div className="mt-1 font-medium">{party?.name ?? "Walk-in customer"}</div>
        {party?.phone && <div className="text-sm text-muted-foreground">{party.phone}</div>}
        {party?.gstNumber && <div className="text-sm text-muted-foreground">GSTIN: {party.gstNumber}</div>}
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
            {items.map((it) => (
              <TR key={it.id} className="hover:bg-transparent">
                <TD>{it.description}</TD>
                <TD className="text-right tabular-nums">{it.quantity}</TD>
                <TD className="text-right tabular-nums">{money(it.unitPrice, currency)}</TD>
                <TD className="text-right tabular-nums">{money(it.lineTotal, currency)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </div>

      <div className="flex justify-end">
        <div className="w-full max-w-xs space-y-1.5 text-sm">
          <Row label="Subtotal" value={money(sale.subtotal, currency)} />
          {sale.discountAmount > 0 && (
            <div className="flex justify-between text-success">
              <span>
                Discount
                {sale.discountType === "percentage" ? ` (${sale.discountValue}%)` : ""}
              </span>
              <span className="tabular-nums">- {money(sale.discountAmount, currency)}</span>
            </div>
          )}
          <Row label="Tax" value={money(sale.tax, currency)} />
          <div className="flex justify-between border-t border-border pt-2 text-base font-semibold">
            <span>Total</span>
            <span className="tabular-nums">{money(sale.total, currency)}</span>
          </div>
          <Row label="Paid" value={money(sale.amountPaid, currency)} />
          <div className="flex justify-between font-medium text-warning">
            <span>Balance due</span>
            <span className="tabular-nums">{money(cancelled ? 0 : due, currency)}</span>
          </div>
        </div>
      </div>

      {sale.notes && (
        <p className="border-t border-border pt-4 text-sm text-muted-foreground">
          <span className="font-medium text-foreground">Notes: </span>
          {sale.notes}
        </p>
      )}

      <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border pt-4">
        <Link
          href={`/sales/${sale.id}`}
          className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
        >
          Open full invoice <Icon name="chevronRight" size={15} />
        </Link>
        {!cancelled && due > 0 && (
          <RecordPaymentButton
            action={recordSalePaymentAction}
            idName="saleId"
            idValue={sale.id}
            due={due}
            currency={currency}
            variant="primary"
          />
        )}
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className="tabular-nums">{value}</span>
    </div>
  );
}
