import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "./ui/button";
import { Input, Select } from "./ui/input";
import { Icon } from "./Icon";
import { money, round2 } from "@/lib/utils";

export interface EditorProduct {
  id: string;
  name: string;
  unit: string;
  sellingPrice: number;
  purchasePrice: number;
}

export interface LineRow {
  productId: string | null;
  description: string;
  quantity: number;
  unitPrice: number;
}

interface Row extends LineRow {
  key: number;
}

export function LineItemsEditor({
  products,
  priceField,
  taxRate,
  currency,
  initialRows,
  discountType = "none",
  discountValue = 0,
  onChange,
}: {
  products: EditorProduct[];
  priceField: "sellingPrice" | "purchasePrice";
  taxRate: number;
  currency: string;
  initialRows?: LineRow[];
  /** Live discount folded into the shown totals. */
  discountType?: "none" | "amount" | "percentage";
  discountValue?: number;
  /** Fires on every edit so the parent can submit / persist the working rows. */
  onChange?: (rows: LineRow[]) => void;
}) {
  const counter = useRef(initialRows && initialRows.length > 0 ? initialRows.length : 1);
  const [rows, setRows] = useState<Row[]>(() =>
    initialRows && initialRows.length > 0
      ? initialRows.map((r, i) => ({ ...r, key: i }))
      : [{ key: 0, productId: null, description: "", quantity: 1, unitPrice: 0 }],
  );

  function update(key: number, patch: Partial<Row>) {
    setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }
  function onProduct(key: number, productId: string) {
    const p = products.find((x) => x.id === productId);
    if (p) update(key, { productId, description: p.name, unitPrice: p[priceField] });
    else update(key, { productId: null });
  }
  function addRow() {
    setRows((rs) => [
      ...rs,
      { key: counter.current++, productId: null, description: "", quantity: 1, unitPrice: 0 },
    ]);
  }
  function removeRow(key: number) {
    setRows((rs) => (rs.length > 1 ? rs.filter((r) => r.key !== key) : rs));
  }

  const subtotal = useMemo(
    () => round2(rows.reduce((a, r) => a + (r.quantity || 0) * (r.unitPrice || 0), 0)),
    [rows],
  );

  // Discount applies to the subtotal before tax, mirroring the server so the
  // preview matches exactly what gets stored.
  const discountAmount =
    discountType === "amount"
      ? round2(Math.max(0, discountValue))
      : discountType === "percentage"
        ? round2((subtotal * Math.max(0, discountValue)) / 100)
        : 0;
  const overDiscount = discountType !== "none" && discountAmount > subtotal;
  const discountedSubtotal = round2(Math.max(0, subtotal - discountAmount));
  const tax = round2(discountedSubtotal * (taxRate / 100));
  const total = round2(discountedSubtotal + tax);

  useEffect(() => {
    onChange?.(
      rows.map(({ productId, description, quantity, unitPrice }) => ({
        productId,
        description,
        quantity,
        unitPrice,
      })),
    );
    // Only depend on rows: onChange identity may change every parent render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows]);

  return (
    <div className="flex flex-col gap-2">
      <div className="hidden grid-cols-[1fr_5rem_6rem_6rem_2rem] gap-2 px-1 text-xs font-medium text-muted-foreground sm:grid">
        <span>Item</span>
        <span className="text-right">Qty</span>
        <span className="text-right">Price</span>
        <span className="text-right">Total</span>
        <span />
      </div>

      {rows.map((r) => (
        <div
          key={r.key}
          className="grid grid-cols-2 gap-2 rounded-lg border border-border p-2 sm:grid-cols-[1fr_5rem_6rem_6rem_2rem] sm:border-0 sm:p-0"
        >
          <div className="col-span-2 flex flex-col gap-1 sm:col-span-1">
            {products.length > 0 && (
              <Select value={r.productId ?? ""} onChange={(e) => onProduct(r.key, e.target.value)}>
                <option value="">Custom item…</option>
                {products.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </Select>
            )}
            <Input
              placeholder="Description"
              value={r.description}
              onChange={(e) => update(r.key, { description: e.target.value })}
            />
          </div>
          <Input
            type="number"
            min={0}
            step="1"
            className="text-right"
            value={r.quantity}
            onChange={(e) => update(r.key, { quantity: Number(e.target.value) })}
            aria-label="Quantity"
          />
          <Input
            type="number"
            min={0}
            step="0.01"
            className="text-right"
            value={r.unitPrice}
            onChange={(e) => update(r.key, { unitPrice: Number(e.target.value) })}
            aria-label="Unit price"
          />
          <div className="flex items-center justify-end text-sm font-medium tabular-nums">
            {money((r.quantity || 0) * (r.unitPrice || 0), currency)}
          </div>
          <button
            type="button"
            onClick={() => removeRow(r.key)}
            className="flex items-center justify-center text-muted-foreground hover:text-destructive"
            aria-label="Remove row"
          >
            <Icon name="trash" size={16} />
          </button>
        </div>
      ))}

      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={addRow}
        className="mt-1 self-start"
      >
        <Icon name="plus" size={16} /> Add item
      </Button>

      <div className="mt-2 space-y-1 rounded-lg bg-muted/50 p-3 text-sm">
        <div className="flex justify-between">
          <span className="text-muted-foreground">Subtotal</span>
          <span className="tabular-nums">{money(subtotal, currency)}</span>
        </div>
        {discountAmount > 0 && (
          <div className="flex justify-between text-success">
            <span>Discount{discountType === "percentage" ? ` (${discountValue}%)` : ""}</span>
            <span className="tabular-nums">- {money(discountAmount, currency)}</span>
          </div>
        )}
        <div className="flex justify-between">
          <span className="text-muted-foreground">Tax ({taxRate}%)</span>
          <span className="tabular-nums">{money(tax, currency)}</span>
        </div>
        <div className="flex justify-between border-t border-border pt-1 font-semibold">
          <span>Total</span>
          <span className="tabular-nums">{money(total, currency)}</span>
        </div>
        {overDiscount && (
          <p className="flex items-center gap-1 pt-1 text-xs text-destructive">
            <Icon name="alert" size={13} />
            Discount is more than the subtotal, lower it before publishing.
          </p>
        )}
      </div>
    </div>
  );
}
