import { useEffect, useState } from "react";
import { api, useApi, useMutation } from "@/lib/api";
import { PageHeader, PageState, EmptyState, SectionCard } from "@/components/ui/misc";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Field, Input } from "@/components/ui/input";
import { Pagination, type PageInfo } from "@/components/ui/pagination";
import { Icon } from "@/components/Icon";
import { ConfirmButton } from "@/components/ConfirmButton";
import { Can, PERMISSIONS, useCan } from "@/lib/session";
import { cn, timeAgo } from "@/lib/utils";

interface DraftItem {
  productId: string | null;
  description: string;
  quantity: number;
  unitPrice: number;
}

interface Draft {
  suggestedType: string;
  partyId: string | null;
  partyName: string | null;
  items: DraftItem[];
  amount: number | null;
  category: string | null;
  date: string | null;
  engine: string;
}

interface InboxRow {
  id: string;
  channel: string;
  sender: string;
  senderName: string | null;
  subject: string | null;
  body: string;
  status: string;
  statusLabel: string;
  draft: Draft | null;
  note: string | null;
  receivedAt: string;
  handledAt: string | null;
}

interface InboxData {
  rows: InboxRow[];
  page: PageInfo;
  counts: Record<string, number>;
  pending: number;
  inboxToken: string;
  inboxAddress: string;
  channels: { email: boolean; telegram: boolean };
  links: { id: string; channel: string; label: string | null; externalId: string }[];
}

const STATUS_TONE: Record<string, "info" | "success" | "warning" | "destructive" | "default"> = {
  pending: "warning",
  accepted: "success",
  rejected: "default",
  failed: "destructive",
};

/** The backend collects every 30s; this is how long the open page waits before
 *  asking what it found. */
const REFRESH_MS = 15_000;

const FILTERS = [
  { value: "", label: "All" },
  { value: "pending", label: "Needs review" },
  { value: "accepted", label: "Recorded" },
  { value: "rejected", label: "Dismissed" },
  { value: "failed", label: "Could not read" },
];

/** Orders that arrived by email or Telegram, waiting to be confirmed. Nothing
 *  here has touched the books yet — that is what Record does. */
export function Inbox() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [open, setOpen] = useState<InboxRow | null>(null);
  const [showSetup, setShowSetup] = useState(false);
  const query = new URLSearchParams({ page: String(page) });
  if (status) query.set("status", status);
  const { data, loading, error, reload } = useApi<InboxData>(`/inbox?${query}`);
  const { run, pending, error: actionError } = useMutation();
  const can = useCan();

  // The page is a queue, so it refreshes itself. "Check now" stays, but only
  // to force a sweep this second rather than waiting for the next one — it is
  // not how you find out something arrived. Paused while a message is open or
  // a decision is in flight, so the list never moves under a click.
  const busy = open !== null || pending;
  useEffect(() => {
    if (busy) return;
    const id = setInterval(reload, REFRESH_MS);
    return () => clearInterval(id);
  }, [busy, reload]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Inbox"
        description="Orders that arrived by email or Telegram. Nothing is recorded until you confirm it."
      >
        <Can do={PERMISSIONS.txnWrite}>
          <Button
            variant="outline"
            disabled={pending}
            onClick={() => run(() => api.post("/inbox/collect"), reload)}
          >
            <Icon name="refresh" size={16} /> Check now
          </Button>
        </Can>
        <Button variant="secondary" onClick={() => setShowSetup(true)}>
          <Icon name="settings" size={16} /> Set up channels
        </Button>
      </PageHeader>

      {/* Only before the first load. Once the list is on screen a background
          refresh must not replace it with skeletons every fifteen seconds. */}
      {(!data || error) && <PageState loading={loading} error={error} />}

      {/* A refused action says so. "Check now" needs `txn:write`, which an
          admin does not hold, and a button that fails in silence is worse than
          one that is not there. */}
      {actionError && (
        <p className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {actionError}
        </p>
      )}

      {data && !data.channels.email && !data.channels.telegram && (
        <p className="flex items-start gap-2 rounded-xl border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-warning">
          <Icon name="alert" size={16} className="mt-0.5 shrink-0" />
          <span>
            <strong>No channel is switched on</strong>, so nothing is being collected — mail can sit
            in the mailbox unread and this page will look the same as an empty one. Start with{" "}
            <code className="font-mono">{".\\run-dev.ps1 -WithEmail"}</code>, or set{" "}
            <code className="font-mono">EMAIL_INGEST_ENABLED=true</code> and{" "}
            <code className="font-mono">TELEGRAM_BOT_TOKEN</code> in{" "}
            <code className="font-mono">backend/.env</code>.
          </span>
        </p>
      )}

      {data && data.channels.email !== data.channels.telegram && (
        <p className="text-sm text-muted-foreground">
          Collecting from <strong>{data.channels.email ? "email" : "Telegram"}</strong> only.{" "}
          {data.channels.email
            ? "Telegram is off until TELEGRAM_BOT_TOKEN is set."
            : "Email is off until EMAIL_INGEST_ENABLED is true — start with -WithEmail."}
        </p>
      )}

      {data && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            {FILTERS.map((f) => (
              <button
                key={f.value}
                type="button"
                onClick={() => {
                  setStatus(f.value);
                  setPage(1);
                }}
                className={cn(
                  "rounded-full border px-3 py-1 text-xs font-medium transition-colors focus-visible:focus-ring",
                  status === f.value
                    ? "border-transparent bg-accent text-accent-foreground"
                    : "border-border text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                {f.label}
                {f.value && data.counts[f.value] ? ` (${data.counts[f.value]})` : ""}
              </button>
            ))}
          </div>

          <SectionCard
            title="Messages"
            description={
              data.pending
                ? `${data.pending} waiting for review`
                : "Nothing waiting — new orders appear here automatically"
            }
          >
            {data.rows.length === 0 ? (
              <div className="p-6">
                <EmptyState
                  icon={<Icon name="bell" />}
                  title="No messages yet"
                  description="Mail sent to your inbox address, or a message to your linked Telegram chat, will appear here."
                  action={
                    <Button variant="outline" onClick={() => setShowSetup(true)}>
                      Set up channels
                    </Button>
                  }
                />
              </div>
            ) : (
              <ul className="divide-y divide-border">
                {data.rows.map((row) => (
                  <li key={row.id} className="flex items-start gap-3 p-4">
                    <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                      <Icon name={row.channel === "telegram" ? "input" : "expenses"} size={15} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">
                          {row.subject || row.body.slice(0, 60) || "(no subject)"}
                        </span>
                        <Badge tone={STATUS_TONE[row.status] ?? "default"}>{row.statusLabel}</Badge>
                      </div>
                      <p className="mt-0.5 text-sm text-muted-foreground">
                        {row.senderName ? `${row.senderName} · ` : ""}
                        {row.sender} · {row.channel}
                      </p>
                      {row.draft && (
                        <p className="mt-1 text-sm">
                          Read as <span className="font-medium">{row.draft.suggestedType}</span>
                          {row.draft.partyName ? ` for ${row.draft.partyName}` : ""}
                          {row.draft.items?.length
                            ? ` · ${row.draft.items
                                .map((i) => `${i.quantity} × ${i.description}`)
                                .join(", ")}`
                            : ""}
                        </p>
                      )}
                      {row.note && <p className="mt-1 text-sm text-destructive">{row.note}</p>}
                      <p className="mt-1 text-xs text-muted-foreground">
                        {timeAgo(row.receivedAt)}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      {row.status === "pending" && can(PERMISSIONS.txnWrite) && (
                        <Button size="sm" onClick={() => setOpen(row)}>
                          Review
                        </Button>
                      )}
                      {(row.status === "pending" || row.status === "failed") &&
                        can(PERMISSIONS.txnWrite) && (
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={pending}
                            onClick={() => run(() => api.post(`/inbox/${row.id}/reject`), reload)}
                          >
                            Dismiss
                          </Button>
                        )}
                      <ConfirmButton
                        needs={PERMISSIONS.dataManage}
                        danger
                        title="Delete this message"
                        message="It will be removed from the inbox entirely."
                        confirmLabel="Delete"
                        action={() => api.del(`/inbox/${row.id}`)}
                        onDone={reload}
                      >
                        <Icon name="trash" size={15} />
                      </ConfirmButton>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {data.page && <Pagination page={data.page} onChange={setPage} label="messages" />}
          </SectionCard>

          <Can do={PERMISSIONS.dataManage}>
            <div className="flex justify-end">
              <Button
                variant="outline"
                size="sm"
                disabled={pending}
                onClick={() => run(() => api.post("/inbox/clear-handled"), reload)}
              >
                Clear handled messages
              </Button>
            </div>
          </Can>
        </>
      )}

      <ReviewModal row={open} onClose={() => setOpen(null)} onDone={reload} />
      <SetupModal
        open={showSetup}
        data={data}
        onClose={() => setShowSetup(false)}
        onDone={reload}
      />
    </div>
  );
}

/** The confirm screen. The draft is editable because the parser is a
 *  suggestion, not an authority. */
function ReviewModal({
  row,
  onClose,
  onDone,
}: {
  row: InboxRow | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { run, pending, error } = useMutation();
  const [items, setItems] = useState<DraftItem[]>([]);
  const [loadedFor, setLoadedFor] = useState<string | null>(null);

  if (row && loadedFor !== row.id) {
    setLoadedFor(row.id);
    setItems(row.draft?.items?.length ? row.draft.items : []);
  }

  async function record() {
    if (!row) return;
    await run(
      // `type` explicitly: the draft names it `suggestedType`, and the publish
      // path defaults to "sale" when it cannot find one.
      () =>
        api.post(`/inbox/${row.id}/accept`, {
          ...row.draft,
          type: row.draft?.suggestedType ?? "sale",
          items,
        }),
      () => {
        onDone();
        onClose();
      },
    );
  }

  function patch(index: number, changes: Partial<DraftItem>) {
    setItems((rows) => rows.map((r, i) => (i === index ? { ...r, ...changes } : r)));
  }

  return (
    <Modal
      open={row !== null}
      onClose={onClose}
      title="Review this order"
      description={row ? `From ${row.sender} via ${row.channel}` : undefined}
    >
      <div className="flex flex-col gap-4 p-5">
        {row && (
          <Card className="p-3">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              What they wrote
            </p>
            <p className="mt-1 whitespace-pre-wrap text-sm">{row.body || "(empty)"}</p>
          </Card>
        )}

        <div className="flex flex-col gap-3">
          {items.map((item, index) => (
            <div key={index} className="grid grid-cols-[1fr_5rem_6rem] gap-2">
              <Field label={index === 0 ? "Item" : undefined}>
                <Input
                  value={item.description}
                  onChange={(e) => patch(index, { description: e.target.value })}
                />
              </Field>
              <Field label={index === 0 ? "Qty" : undefined}>
                <Input
                  type="number"
                  value={item.quantity}
                  onChange={(e) => patch(index, { quantity: Number(e.target.value) })}
                />
              </Field>
              <Field label={index === 0 ? "Price" : undefined}>
                <Input
                  type="number"
                  value={item.unitPrice}
                  onChange={(e) => patch(index, { unitPrice: Number(e.target.value) })}
                />
              </Field>
            </div>
          ))}
          {items.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Nothing was extracted from this message. Dismiss it, or record the order by hand.
            </p>
          )}
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button onClick={record} disabled={pending || items.length === 0}>
            {pending ? "Recording…" : "Record it"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

/** How to get mail and messages flowing in. */
function SetupModal({
  open,
  data,
  onClose,
  onDone,
}: {
  open: boolean;
  data: InboxData | undefined;
  onClose: () => void;
  onDone: () => void;
}) {
  const { run, pending } = useMutation();
  const token = data?.inboxToken ?? "";
  // The server composes the address, because it owns the domain setting; the
  // fallback only matters for a cached response from an older build.
  const address = data?.inboxAddress ?? `orders+${token}@smartsme.local`;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Set up channels"
      description="Two ways for orders to reach this business."
      className="max-w-xl"
    >
      <div className="flex flex-col gap-5 p-5">
        <div>
          <p className="font-medium">Email</p>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Have customers send orders to this address. The token is what routes mail to your
            business, so treat it like a private link.
          </p>
          <Input
            readOnly
            value={address}
            className="mt-2"
            onFocus={(e) => e.currentTarget.select()}
          />
        </div>

        <div>
          <p className="font-medium">Telegram</p>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Message your SmartSME bot with the command below, once. Everything that chat sends
            afterwards lands here.
          </p>
          <Input
            readOnly
            value={`/link ${token}`}
            className="mt-2"
            onFocus={(e) => e.currentTarget.select()}
          />
        </div>

        {data && data.links.length > 0 && (
          <div>
            <p className="font-medium">Linked chats</p>
            <ul className="mt-2 flex flex-col gap-2">
              {data.links.map((link) => (
                <li
                  key={link.id}
                  className="flex items-center justify-between rounded-lg border border-border px-3 py-2 text-sm"
                >
                  <span>
                    {link.label || link.externalId}{" "}
                    <span className="text-muted-foreground">· {link.channel}</span>
                  </span>
                  {/* Unlinking a chat is configuration, so the API asks for
                      `config:write`. Offering it to an employee only produced a
                      button that answered 403 into nothing. */}
                  <Can do={PERMISSIONS.configWrite}>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={pending}
                      onClick={() => run(() => api.del(`/inbox/links/${link.id}`), onDone)}
                    >
                      Unlink
                    </Button>
                  </Can>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="flex justify-end">
          <Button onClick={onClose}>Done</Button>
        </div>
      </div>
    </Modal>
  );
}
