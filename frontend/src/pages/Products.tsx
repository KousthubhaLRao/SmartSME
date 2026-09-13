import { useState } from "react";
import { api, useApi, useMutation } from "@/lib/api";
import { PageHeader, PageState, StatCard, EmptyState, SectionCard } from "@/components/ui/misc";
import { Card } from "@/components/ui/card";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Field, Input } from "@/components/ui/input";
import { Icon } from "@/components/Icon";
import { ConfirmButton } from "@/components/ConfirmButton";
import { Can, PERMISSIONS } from "@/lib/session";
import { cn, formatDateTime, money } from "@/lib/utils";

interface ProductRow {
  id: string;
  name: string;
  sku: string | null;
  hsn: string | null;
  unit: string;
  purchasePrice: number;
  sellingPrice: number;
  stock: number;
  lowStockThreshold: number;
  stockValue: number;
  low: boolean;
}

interface Movement {
  id: string;
  productName: string | null;
  delta: number;
  reason: string;
  note: string | null;
  createdAt: string;
}

interface ProductsData {
  rows: ProductRow[];
  movements: Movement[];
  stats: { count: number; inventoryValue: number; lowCount: number };
  currency: string;
}

const BLANK = {
  name: "",
  sku: "",
  hsn: "",
  unit: "pcs",
  purchasePrice: 0,
  sellingPrice: 0,
  stock: 0,
  lowStockThreshold: 10,
};

export function Products() {
  const { data, loading, error, reload } = useApi<ProductsData>("/products");
  const [editing, setEditing] = useState<ProductRow | null>(null);
  const [creating, setCreating] = useState(false);
  const [adjusting, setAdjusting] = useState<ProductRow | null>(null);

  if (!data) return <PageState loading={loading} error={error} />;
  const cur = data.currency;

  return (
    <div className="space-y-6">
      <PageHeader title="Products" description="Inventory, pricing and stock movements.">
        <Can do={PERMISSIONS.catalogWrite}>
          <Button onClick={() => setCreating(true)}>
            <Icon name="plus" size={16} /> New product
          </Button>
        </Can>
      </PageHeader>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Products"
          value={data.stats.count}
          icon={<Icon name="products" />}
          tone="primary"
        />
        <StatCard
          label="Inventory value"
          value={money(data.stats.inventoryValue, cur)}
          icon={<Icon name="box" />}
          tone="info"
        />
        <StatCard
          label="Low stock"
          value={data.stats.lowCount}
          icon={<Icon name="alert" />}
          tone="warning"
        />
      </div>

      <Card>
        {data.rows.length === 0 ? (
          <div className="p-6">
            <EmptyState
              icon={<Icon name="products" />}
              title="No products yet"
              description="Add products to track stock and pricing."
            />
          </div>
        ) : (
          <Table>
            <THead>
              <TR className="hover:bg-transparent">
                <TH>Product</TH>
                <TH>Unit</TH>
                <TH className="text-right">Buy</TH>
                <TH className="text-right">Sell</TH>
                <TH className="text-right">Stock</TH>
                <TH className="text-right">Value</TH>
                <TH className="text-right">Actions</TH>
              </TR>
            </THead>
            <TBody>
              {data.rows.map((p) => (
                <TR key={p.id}>
                  <TD>
                    <div className="font-medium">{p.name}</div>
                    <div className="text-xs text-muted-foreground">
                      {[p.sku, p.hsn && `HSN ${p.hsn}`].filter(Boolean).join(" · ") || "-"}
                    </div>
                  </TD>
                  <TD className="text-muted-foreground">{p.unit}</TD>
                  <TD className="text-right tabular-nums">{money(p.purchasePrice, cur)}</TD>
                  <TD className="text-right tabular-nums">{money(p.sellingPrice, cur)}</TD>
                  <TD className="text-right">
                    <span
                      className={cn(
                        "tabular-nums font-medium",
                        p.stock <= 0 ? "text-destructive" : p.low && "text-warning",
                      )}
                    >
                      {p.stock}
                    </span>
                    {p.stock <= 0 ? (
                      <Badge tone="destructive" className="ml-2">
                        Out
                      </Badge>
                    ) : p.low ? (
                      <Badge tone="warning" className="ml-2">
                        Low
                      </Badge>
                    ) : null}
                  </TD>
                  <TD className="text-right tabular-nums">{money(p.stockValue, cur)}</TD>
                  <TD>
                    <div className="flex items-center justify-end gap-1">
                      <Button variant="outline" size="sm" onClick={() => setAdjusting(p)}>
                        Adjust
                      </Button>
                      <button
                        onClick={() => setEditing(p)}
                        aria-label="Edit product"
                        className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
                      >
                        <Icon name="edit" size={16} />
                      </button>
                      <ConfirmButton
                        needs={PERMISSIONS.dataManage}
                        action={() => api.del(`/products/${p.id}`)}
                        title="Delete product?"
                        message={`"${p.name}" will be removed. Products that appear on past invoices cannot be deleted.`}
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

      <SectionCard
        title="Recent stock movements"
        description="Every change to inventory, with its cause"
      >
        {data.movements.length === 0 ? (
          <div className="p-6">
            <EmptyState icon={<Icon name="box" />} title="No movements yet" />
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {data.movements.map((m) => (
              <li key={m.id} className="flex items-center gap-3 px-5 py-3 text-sm">
                <span
                  className={cn(
                    "flex h-8 w-8 items-center justify-center rounded-lg",
                    m.delta > 0
                      ? "bg-success/15 text-success"
                      : "bg-destructive/15 text-destructive",
                  )}
                >
                  <Icon name={m.delta > 0 ? "trendingUp" : "trendingDown"} size={15} />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{m.productName ?? "Product"}</div>
                  <div className="text-xs text-muted-foreground">
                    {m.reason} · {m.note ?? "-"} · {formatDateTime(m.createdAt)}
                  </div>
                </div>
                <span
                  className={cn(
                    "tabular-nums font-medium",
                    m.delta > 0 ? "text-success" : "text-destructive",
                  )}
                >
                  {m.delta > 0 ? `+${m.delta}` : m.delta}
                </span>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      <ProductDialog
        open={creating || editing !== null}
        product={editing}
        onClose={() => {
          setCreating(false);
          setEditing(null);
        }}
        onSaved={() => {
          setCreating(false);
          setEditing(null);
          reload();
        }}
      />

      <AdjustDialog
        product={adjusting}
        onClose={() => setAdjusting(null)}
        onSaved={() => {
          setAdjusting(null);
          reload();
        }}
      />
    </div>
  );
}

function ProductDialog({
  open,
  product,
  onClose,
  onSaved,
}: {
  open: boolean;
  product: ProductRow | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { run, pending, error } = useMutation();
  const [form, setForm] = useState(BLANK);
  const [seeded, setSeeded] = useState<string | null>(null);

  // Seed the form when the dialog opens for a different product.
  const key = product?.id ?? (open ? "new" : null);
  if (open && key !== seeded) {
    setSeeded(key);
    setForm(
      product
        ? {
            name: product.name,
            sku: product.sku ?? "",
            hsn: product.hsn ?? "",
            unit: product.unit,
            purchasePrice: product.purchasePrice,
            sellingPrice: product.sellingPrice,
            stock: product.stock,
            lowStockThreshold: product.lowStockThreshold,
          }
        : BLANK,
    );
  }
  if (!open && seeded !== null) setSeeded(null);

  const num =
    (k: "purchasePrice" | "sellingPrice" | "stock" | "lowStockThreshold") =>
    (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm((f) => ({ ...f, [k]: Number(e.target.value) || 0 }));
  const text = (k: "name" | "sku" | "hsn" | "unit") => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    await run(
      () => (product ? api.put(`/products/${product.id}`, form) : api.post("/products", form)),
      onSaved,
    );
  }

  return (
    <Modal open={open} onClose={onClose} title={product ? "Edit product" : "New product"}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Field label="Name">
          <Input value={form.name} onChange={text("name")} placeholder="Rice Bag 25kg" required />
        </Field>
        <div className="grid grid-cols-3 gap-3">
          <Field label="SKU">
            <Input value={form.sku} onChange={text("sku")} placeholder="RICE-25" />
          </Field>
          <Field label="HSN">
            <Input value={form.hsn} onChange={text("hsn")} placeholder="1006" />
          </Field>
          <Field label="Unit">
            <Input value={form.unit} onChange={text("unit")} placeholder="bag" />
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Purchase price">
            <Input
              type="number"
              min={0}
              step="0.01"
              value={form.purchasePrice}
              onChange={num("purchasePrice")}
            />
          </Field>
          <Field label="Selling price">
            <Input
              type="number"
              min={0}
              step="0.01"
              value={form.sellingPrice}
              onChange={num("sellingPrice")}
            />
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          {!product && (
            <Field label="Opening stock">
              <Input type="number" min={0} step="1" value={form.stock} onChange={num("stock")} />
            </Field>
          )}
          <Field label="Low-stock threshold">
            <Input
              type="number"
              min={0}
              step="1"
              value={form.lowStockThreshold}
              onChange={num("lowStockThreshold")}
            />
          </Field>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button type="submit" disabled={pending}>
            {pending ? "Saving…" : product ? "Save changes" : "Add product"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function AdjustDialog({
  product,
  onClose,
  onSaved,
}: {
  product: ProductRow | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { run, pending, error } = useMutation();
  const [delta, setDelta] = useState(0);
  const [note, setNote] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!product) return;
    await run(
      () => api.post(`/products/${product.id}/adjust`, { delta, note }),
      () => {
        setDelta(0);
        setNote("");
        onSaved();
      },
    );
  }

  return (
    <Modal open={product !== null} onClose={onClose} title="Adjust stock" className="max-w-md">
      {product && (
        <form onSubmit={submit} className="flex flex-col gap-4">
          <p className="text-sm text-muted-foreground">
            {product.name} currently has{" "}
            <span className="font-medium text-foreground">
              {product.stock} {product.unit}
            </span>
            .
          </p>
          <Field label="Change" hint="Use a negative number to reduce stock (damage, correction).">
            <Input
              type="number"
              step="1"
              value={delta || ""}
              onChange={(e) => setDelta(Number(e.target.value) || 0)}
              autoFocus
            />
          </Field>
          <Field label="Note">
            <Input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Stock audit correction"
            />
          </Field>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={pending}>
              Cancel
            </Button>
            <Button type="submit" disabled={pending || delta === 0}>
              {pending ? "Saving…" : "Apply adjustment"}
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}
