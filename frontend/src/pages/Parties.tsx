import { Fragment, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, useApi, useMutation } from "@/lib/api";
import { PageHeader, PageState, StatCard, EmptyState } from "@/components/ui/misc";
import { Card } from "@/components/ui/card";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import { Pagination, type PageInfo } from "@/components/ui/pagination";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Icon } from "@/components/Icon";
import { ConfirmButton } from "@/components/ConfirmButton";
import { COUNTRIES, flagEmoji, splitPhone } from "@/lib/countries";
import { Can, PERMISSIONS } from "@/lib/session";
import { cn, formatDate, money, round2 } from "@/lib/utils";

interface OutstandingDoc {
  id: string;
  ref: string;
  date: string;
  total: number;
  due: number;
}

interface PartyRow {
  id: string;
  type: string;
  name: string;
  phone: string | null;
  email: string | null;
  gstNumber: string | null;
  address: string | null;
  balance: number;
  outstanding: OutstandingDoc[];
}

interface PartiesData {
  rows: PartyRow[];
  page: PageInfo;
  stats: { receivable: number; payable: number };
  currency: string;
}

export function Parties() {
  const [params, setParams] = useSearchParams();
  const filter = (() => {
    const t = params.get("type");
    return t === "customer" || t === "supplier" ? t : "all";
  })();

  const [page, setPage] = useState(1);
  const { data, loading, error, reload } = useApi<PartiesData>(`/parties?page=${page}`);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [editing, setEditing] = useState<PartyRow | null>(null);
  const [creating, setCreating] = useState(false);

  if (!data) return <PageState loading={loading} error={error} />;
  const cur = data.currency;

  const visible = filter === "all" ? data.rows : data.rows.filter((p) => p.type === filter);
  const tabs = [
    { key: "all", label: `All (${data.rows.length})` },
    {
      key: "customer",
      label: `Customers (${data.rows.filter((p) => p.type === "customer").length})`,
    },
    {
      key: "supplier",
      label: `Suppliers (${data.rows.filter((p) => p.type === "supplier").length})`,
    },
  ];

  const showReceivables = (filter === "all" || filter === "customer") && data.stats.receivable > 0;
  const showPayables = (filter === "all" || filter === "supplier") && data.stats.payable > 0;

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Parties" description="Customers and suppliers, with outstanding balances.">
        <Can do={PERMISSIONS.catalogWrite}>
          <Button onClick={() => setCreating(true)}>
            <Icon name="plus" size={16} /> New party
          </Button>
        </Can>
      </PageHeader>

      <div className="grid gap-4 sm:grid-cols-2">
        <StatCard
          label="Total receivable"
          value={money(data.stats.receivable, cur)}
          sub="Owed to you by customers"
          icon={<Icon name="trendingUp" />}
          tone="success"
        />
        <StatCard
          label="Total payable"
          value={money(data.stats.payable, cur)}
          sub="Owed by you to suppliers"
          icon={<Icon name="trendingDown" />}
          tone="warning"
        />
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex gap-1 rounded-lg border border-border bg-card p-1 text-sm">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => (t.key === "all" ? setParams({}) : setParams({ type: t.key }))}
              className={cn(
                "rounded-md px-3 py-1.5 font-medium transition-colors",
                filter === t.key
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        {(showReceivables || showPayables) && (
          <div className="flex flex-wrap items-center gap-2">
            {showReceivables && (
              <ConfirmButton
                needs={PERMISSIONS.dataManage}
                action={() => api.post("/parties/settle-all/receivable")}
                title="Mark all receivables as paid?"
                message={`Every outstanding customer invoice (${money(data.stats.receivable, cur)}) will be marked fully paid and balances cleared.`}
                confirmLabel="Mark all as paid"
                onDone={reload}
                className={buttonVariants({ variant: "outline", size: "sm" })}
              >
                <Icon name="check" size={15} /> Receivables paid
              </ConfirmButton>
            )}
            {showPayables && (
              <ConfirmButton
                needs={PERMISSIONS.dataManage}
                action={() => api.post("/parties/settle-all/payable")}
                title="Mark all payables as paid?"
                message={`Every outstanding supplier bill (${money(data.stats.payable, cur)}) will be marked fully paid and balances cleared.`}
                confirmLabel="Mark all as paid"
                onDone={reload}
                className={buttonVariants({ variant: "outline", size: "sm" })}
              >
                <Icon name="check" size={15} /> Payables paid
              </ConfirmButton>
            )}
          </div>
        )}
      </div>

      <Card>
        {visible.length === 0 ? (
          <div className="p-6">
            <EmptyState
              icon={<Icon name="parties" />}
              title="No parties here"
              description="Add customers and suppliers to track balances and transaction history."
            />
          </div>
        ) : (
          <Table>
            <THead>
              <TR className="hover:bg-transparent">
                <TH>Name</TH>
                <TH>Type</TH>
                <TH>Contact</TH>
                <TH>GSTIN</TH>
                <TH className="text-right">Balance</TH>
                <TH className="text-right">Actions</TH>
              </TR>
            </THead>
            <TBody>
              {visible.map((p) => {
                const isCustomer = p.type === "customer";
                const dueSum = round2(p.outstanding.reduce((a, d) => a + d.due, 0));
                const canSettle = p.outstanding.length > 0 && dueSum > 0;
                const isOpen = expanded.has(p.id);

                return (
                  <Fragment key={p.id}>
                    <TR>
                      <TD>
                        <div className="flex items-center gap-2">
                          {canSettle ? (
                            <button
                              type="button"
                              onClick={() => toggle(p.id)}
                              aria-label={isOpen ? "Hide bills" : "Show bills"}
                              aria-expanded={isOpen}
                              className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
                            >
                              <Icon
                                name="chevronRight"
                                size={15}
                                className={cn("transition-transform", isOpen && "rotate-90")}
                              />
                            </button>
                          ) : (
                            <span className="inline-block h-6 w-6 shrink-0" />
                          )}
                          <div className="min-w-0">
                            <div className="font-medium">{p.name}</div>
                            {p.address && (
                              <div className="max-w-xs truncate text-xs text-muted-foreground">
                                {p.address}
                              </div>
                            )}
                          </div>
                        </div>
                      </TD>
                      <TD>
                        <Badge tone={isCustomer ? "info" : "primary"}>
                          {isCustomer ? "Customer" : "Supplier"}
                        </Badge>
                      </TD>
                      <TD className="text-muted-foreground">{p.phone ?? p.email ?? "-"}</TD>
                      <TD className="text-muted-foreground">{p.gstNumber ?? "-"}</TD>
                      <TD className="text-right">
                        <span
                          className={cn(
                            "tabular-nums font-medium",
                            p.balance > 0
                              ? isCustomer
                                ? "text-success"
                                : "text-warning"
                              : "text-muted-foreground",
                          )}
                        >
                          {money(p.balance, cur)}
                        </span>
                        {canSettle && (
                          <div className="text-xs text-muted-foreground">
                            {p.outstanding.length} open {isCustomer ? "invoice" : "bill"}
                            {p.outstanding.length === 1 ? "" : "s"}
                          </div>
                        )}
                      </TD>
                      <TD>
                        <div className="flex items-center justify-end gap-1">
                          {canSettle && (
                            <ConfirmButton
                              // Same permission as taking a payment against a
                              // single invoice: this is that, for one party,
                              // without the clicking.
                              needs={PERMISSIONS.txnWrite}
                              action={() => api.post(`/parties/${p.id}/settle`)}
                              title={isCustomer ? "Mark invoices as paid?" : "Pay all bills?"}
                              message={`${p.outstanding.length} outstanding ${isCustomer ? "invoice" : "bill"}${
                                p.outstanding.length === 1 ? "" : "s"
                              } for ${p.name} (${money(dueSum, cur)}) will be marked fully paid.`}
                              confirmLabel={isCustomer ? "Mark paid" : "Pay all"}
                              onDone={reload}
                              className={buttonVariants({ variant: "outline", size: "sm" })}
                            >
                              {isCustomer ? "Mark paid" : "Pay all"}
                            </ConfirmButton>
                          )}
                          <button
                            onClick={() => setEditing(p)}
                            aria-label="Edit party"
                            className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
                          >
                            <Icon name="edit" size={16} />
                          </button>
                          <ConfirmButton
                            needs={PERMISSIONS.dataManage}
                            action={() => api.del(`/parties/${p.id}`)}
                            title="Delete party?"
                            message={`"${p.name}" will be removed. Their past transactions are kept but unlinked.`}
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

                    {isOpen && (
                      <TR className="hover:bg-transparent">
                        <TD colSpan={6} className="bg-muted/30 p-0">
                          <div className="px-5 py-3">
                            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                              Outstanding {isCustomer ? "invoices" : "bills"}
                            </div>
                            <ul className="divide-y divide-border rounded-lg border border-border bg-card">
                              {p.outstanding.map((d) => (
                                <li
                                  key={d.id}
                                  className="flex items-center justify-between gap-3 px-4 py-2 text-sm"
                                >
                                  <div className="min-w-0">
                                    <span className="font-medium">{d.ref}</span>
                                    <span className="ml-2 text-xs text-muted-foreground">
                                      {formatDate(d.date)}
                                    </span>
                                  </div>
                                  <div className="flex items-center gap-6 tabular-nums">
                                    <span className="text-muted-foreground">
                                      Total {money(d.total, cur)}
                                    </span>
                                    <span className="font-medium text-warning">
                                      Due {money(d.due, cur)}
                                    </span>
                                  </div>
                                </li>
                              ))}
                            </ul>
                          </div>
                        </TD>
                      </TR>
                    )}
                  </Fragment>
                );
              })}
            </TBody>
          </Table>
        )}
        {data?.page && <Pagination page={data.page} onChange={setPage} label="parties" />}
      </Card>

      <PartyDialog
        open={creating || editing !== null}
        party={editing}
        defaultType={filter === "supplier" ? "supplier" : "customer"}
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
    </div>
  );
}

function PartyDialog({
  open,
  party,
  defaultType,
  onClose,
  onSaved,
}: {
  open: boolean;
  party: PartyRow | null;
  defaultType: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { run, pending, error } = useMutation();
  const [seeded, setSeeded] = useState<string | null>(null);
  const [form, setForm] = useState({
    type: defaultType,
    name: "",
    email: "",
    gstNumber: "",
    address: "",
    openingBalance: 0,
  });
  const [phone, setPhone] = useState(() => splitPhone(null));
  const [phoneError, setPhoneError] = useState<string | null>(null);

  const key = party?.id ?? (open ? "new" : null);
  if (open && key !== seeded) {
    setSeeded(key);
    setForm({
      type: party?.type ?? defaultType,
      name: party?.name ?? "",
      email: party?.email ?? "",
      gstNumber: party?.gstNumber ?? "",
      address: party?.address ?? "",
      openingBalance: 0,
    });
    setPhone(splitPhone(party?.phone ?? null));
    setPhoneError(null);
  }
  if (!open && seeded !== null) setSeeded(null);

  const dial = COUNTRIES.find((c) => c.iso === phone.iso)?.dial ?? "";
  const localNumber = phone.number.replace(/[^0-9]/g, "");
  const combinedPhone = localNumber ? `${dial} ${localNumber}` : "";

  function onNumberChange(e: React.ChangeEvent<HTMLInputElement>) {
    const v = e.target.value;
    setPhone((p) => ({ ...p, number: v }));
    setPhoneError(v && !/^[0-9\s-]*$/.test(v) ? "Phone number can only contain digits." : null);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (phone.number && !/^[0-9\s-]*$/.test(phone.number)) {
      setPhoneError("Phone number can only contain digits.");
      return;
    }
    const body = { ...form, phone: combinedPhone || null };
    await run(
      () => (party ? api.put(`/parties/${party.id}`, body) : api.post("/parties", body)),
      onSaved,
    );
  }

  return (
    <Modal open={open} onClose={onClose} title={party ? "Edit party" : "New party"}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Type">
            <Select
              value={form.type}
              onChange={(e) => setForm((f) => ({ ...f, type: e.target.value }))}
            >
              <option value="customer">Customer</option>
              <option value="supplier">Supplier</option>
            </Select>
          </Field>
          <Field label="Name">
            <Input
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="Kumar Traders"
              required
            />
          </Field>
        </div>

        <Field label="Phone">
          <div className="grid grid-cols-[6.5rem_minmax(0,1fr)] gap-2">
            <Select
              aria-label="Country code"
              className="min-w-0"
              value={phone.iso}
              onChange={(e) => setPhone((p) => ({ ...p, iso: e.target.value }))}
            >
              {COUNTRIES.map((c) => (
                <option key={c.iso} value={c.iso}>
                  {flagEmoji(c.iso)} {c.dial} {c.name}
                </option>
              ))}
            </Select>
            <Input
              aria-label="Phone number"
              className="min-w-0"
              placeholder="98765 43210"
              inputMode="tel"
              value={phone.number}
              onChange={onNumberChange}
            />
          </div>
          {phoneError && <p className="mt-1 text-sm text-destructive">{phoneError}</p>}
        </Field>

        <Field label="Email">
          <Input
            type="email"
            value={form.email}
            onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
            placeholder="name@business.com"
          />
        </Field>
        <Field label="GSTIN">
          <Input
            value={form.gstNumber}
            onChange={(e) => setForm((f) => ({ ...f, gstNumber: e.target.value }))}
            placeholder="29ABCDE1234F1Z5"
          />
        </Field>
        <Field label="Address">
          <Textarea
            value={form.address}
            onChange={(e) => setForm((f) => ({ ...f, address: e.target.value }))}
            placeholder="Optional"
          />
        </Field>
        {!party && (
          <Field
            label="Opening balance"
            hint="Amount they owe you (customer) or you owe them (supplier)."
          >
            <Input
              type="number"
              step="0.01"
              value={form.openingBalance || ""}
              onChange={(e) =>
                setForm((f) => ({ ...f, openingBalance: Number(e.target.value) || 0 }))
              }
            />
          </Field>
        )}

        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button type="submit" disabled={pending}>
            {pending ? "Saving…" : party ? "Save changes" : "Add party"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
