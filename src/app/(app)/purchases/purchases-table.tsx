"use client";

import { useState, useTransition } from "react";
import { Modal } from "@/components/ui/modal";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { PaymentBadge, SourceBadge } from "@/components/status";
import { Icon } from "@/components/icons";
import { RecordPaymentButton } from "@/components/record-payment-button";
import { ConfirmButton } from "@/components/confirm-button";
import { Skeleton } from "@/components/ui/misc";
import { money, formatDate, round2 } from "@/lib/utils";
import {
  recordPurchasePaymentAction,
  cancelPurchaseAction,
  loadPurchaseDetailAction,
  type PurchaseDetail,
} from "./actions";

export interface PurchaseListRow {
  id: string;
  referenceNumber: string;
  createdAt: Date;
  partyName: string | null;
  source: string;
  status: string;
  total: number;
  amountPaid: number;
  paymentStatus: string;
}

export function PurchasesTable({ rows, currency }: { rows: PurchaseListRow[]; currency: string }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const [detail, setDetail] = useState<PurchaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, start] = useTransition();

  function openDetail(id: string) {
    setOpenId(id);
    setDetail(null);
    setError(null);
    start(async () => {
      const res = await loadPurchaseDetailAction(id);
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
          {rows.map((purchase) => {
            const due = round2(purchase.total - purchase.amountPaid);
            const cancelled = purchase.status === "cancelled";
            return (
              <TR
                key={purchase.id}
                onClick={() => openDetail(purchase.id)}
                className="cursor-pointer"
              >
                <TD>
                  <div className="font-medium">{purchase.referenceNumber}</div>
                  <div className="text-xs text-muted-foreground">{formatDate(purchase.createdAt)}</div>
                </TD>
                <TD>{purchase.partyName ?? <span className="text-muted-foreground">-</span>}</TD>
                <TD>
                  <SourceBadge source={purchase.source} />
                </TD>
                <TD className="text-right tabular-nums">{money(purchase.total, currency)}</TD>
                <TD className="text-right tabular-nums">{cancelled ? "-" : money(due, currency)}</TD>
                <TD>
                  {cancelled ? <Badge tone="outline">Cancelled</Badge> : <PaymentBadge status={purchase.paymentStatus} />}
                </TD>
                <TD>
                  {/* Stop row-click from firing when using the inline actions. */}
                  <div className="flex items-center justify-end gap-2" onClick={(e) => e.stopPropagation()}>
                    {!cancelled && due > 0 && (
                      <RecordPaymentButton
                        action={recordPurchasePaymentAction}
                        idName="purchaseId"
                        idValue={purchase.id}
                        due={due}
                        currency={currency}
                        label="Pay"
                      />
                    )}
                    {!cancelled && (
                      <ConfirmButton
                        action={cancelPurchaseAction.bind(null, purchase.id)}
                        title="Cancel purchase?"
                        message={`This removes received stock and reverses the payable for ${purchase.referenceNumber}.`}
                        confirmLabel="Cancel purchase"
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
        title={openRow ? `Bill ${openRow.referenceNumber}` : "Purchase"}
        className="max-w-2xl"
      >
        {error ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : loading || !detail ? (
          <DetailSkeleton />
        ) : (
          <PurchaseDetailView detail={detail} currency={currency} />
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

function PurchaseDetailView({ detail, currency }: { detail: PurchaseDetail; currency: string }) {
  const { purchase, party, items } = detail;
  const due = round2(purchase.total - purchase.amountPaid);
  const cancelled = purchase.status === "cancelled";

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm text-muted-foreground">{formatDate(purchase.createdAt)}</div>
        <div className="flex items-center gap-2">
          <SourceBadge source={purchase.source} />
          {cancelled ? <Badge tone="outline">Cancelled</Badge> : <PaymentBadge status={purchase.paymentStatus} />}
        </div>
      </div>

      <div>
        <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Supplier</div>
        <div className="mt-1 font-medium">{party?.name ?? "Unlinked supplier"}</div>
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
          <Row label="Subtotal" value={money(purchase.subtotal, currency)} />
          {purchase.discountAmount > 0 && (
            <div className="flex justify-between text-success">
              <span>
                Discount
                {purchase.discountType === "percentage" ? ` (${purchase.discountValue}%)` : ""}
              </span>
              <span className="tabular-nums">- {money(purchase.discountAmount, currency)}</span>
            </div>
          )}
          <Row label="Tax" value={money(purchase.tax, currency)} />
          <div className="flex justify-between border-t border-border pt-2 text-base font-semibold">
            <span>Total</span>
            <span className="tabular-nums">{money(purchase.total, currency)}</span>
          </div>
          <Row label="Paid" value={money(purchase.amountPaid, currency)} />
          <div className="flex justify-between font-medium text-warning">
            <span>Balance due</span>
            <span className="tabular-nums">{money(cancelled ? 0 : due, currency)}</span>
          </div>
        </div>
      </div>

      {purchase.notes && (
        <p className="border-t border-border pt-4 text-sm text-muted-foreground">
          <span className="font-medium text-foreground">Notes: </span>
          {purchase.notes}
        </p>
      )}

      {!cancelled && due > 0 && (
        <div className="flex items-center justify-end gap-2 border-t border-border pt-4">
          <RecordPaymentButton
            action={recordPurchasePaymentAction}
            idName="purchaseId"
            idValue={purchase.id}
            due={due}
            currency={currency}
            label="Pay"
            variant="primary"
          />
        </div>
      )}
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
