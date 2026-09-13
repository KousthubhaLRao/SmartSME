import { useEffect, useState } from "react";
import { api, useApi, useMutation } from "@/lib/api";
import { PageHeader, PageState, StatCard, EmptyState, SectionCard } from "@/components/ui/misc";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import { Pagination, type PageInfo } from "@/components/ui/pagination";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Icon } from "@/components/Icon";
import { Can, PERMISSIONS } from "@/lib/session";
import { cn, formatDateTime } from "@/lib/utils";

interface EventRow {
  id: string;
  type: string;
  status: string;
  retryCount: number;
  error: string | null;
  /** Name of the user who caused it; null for seeded or system events. */
  actor: string | null;
  createdAt: string;
  processedAt: string | null;
}

interface EventsData {
  rows: EventRow[];
  page: PageInfo;
  counts: { pending: number; processing: number; done: number; dead: number };
  eventTypes: { value: string; label: string }[];
}

const TONE: Record<string, "outline" | "info" | "success" | "warning" | "destructive"> = {
  pending: "outline",
  processing: "info",
  done: "success",
  failed: "warning",
  dead: "destructive",
};

const FILTERS = ["", "pending", "processing", "done", "dead"];

export function Events() {
  const [filter, setFilter] = useState("");
  const [page, setPage] = useState(1);
  const { data, loading, error, reload } = useApi<EventsData>(
    `/events?page=${page}${filter ? `&status=${filter}` : ""}`,
  );
  const { run, pending } = useMutation();

  // The bus is live, so poll while the page is open to watch pending -> done.
  useEffect(() => {
    const id = setInterval(reload, 4000);
    return () => clearInterval(id);
  }, [reload]);

  if (!data) return <PageState loading={loading} error={error} />;
  const labels = new Map(data.eventTypes.map((t) => [t.value, t.label]));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Event bus"
        description="The transactional outbox, draining into the workflow engine."
      >
        <Can do={PERMISSIONS.eventsOperate}>
          <Button
            variant="outline"
            disabled={pending}
            onClick={() => run(() => api.post("/events/drain"), reload)}
          >
            <Icon name="refresh" size={16} /> Drain queue
          </Button>
        </Can>
      </PageHeader>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Pending"
          value={data.counts.pending}
          icon={<Icon name="clock" />}
          tone="warning"
        />
        <StatCard
          label="Processing"
          value={data.counts.processing}
          icon={<Icon name="refresh" />}
          tone="info"
        />
        <StatCard
          label="Done"
          value={data.counts.done}
          icon={<Icon name="check" />}
          tone="success"
        />
        <StatCard
          label="Dead-letter"
          value={data.counts.dead}
          icon={<Icon name="alert" />}
          tone="destructive"
        />
      </div>

      <div className="flex flex-wrap gap-1 rounded-lg border border-border bg-card p-1 text-sm">
        {FILTERS.map((s) => (
          <button
            key={s || "all"}
            onClick={() => {
              setPage(1);
              setFilter(s);
            }}
            className={cn(
              "rounded-md px-3 py-1.5 font-medium capitalize transition-colors",
              filter === s
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {s === "" ? "All" : s}
          </button>
        ))}
      </div>

      <SectionCard title="Recent events" description="Newest first, up to 100">
        {data.rows.length === 0 ? (
          <div className="p-6">
            <EmptyState
              icon={<Icon name="events" />}
              title="No events"
              description="Events appear here as you record business activity."
            />
          </div>
        ) : (
          <Table>
            <THead>
              <TR className="hover:bg-transparent">
                <TH>Event</TH>
                <TH>Status</TH>
                <TH>By</TH>
                <TH className="text-right">Retries</TH>
                <TH>Created</TH>
                <TH>Processed</TH>
                <TH className="text-right">Actions</TH>
              </TR>
            </THead>
            <TBody>
              {data.rows.map((e) => (
                <TR key={e.id}>
                  <TD>
                    <div className="font-medium">{labels.get(e.type) ?? e.type}</div>
                    {e.error && (
                      <div className="max-w-md truncate text-xs text-destructive">{e.error}</div>
                    )}
                  </TD>
                  <TD>
                    <Badge tone={TONE[e.status] ?? "outline"}>{e.status}</Badge>
                  </TD>
                  <TD className="text-muted-foreground">
                    {e.actor ?? <span className="text-muted-foreground/60">System</span>}
                  </TD>
                  <TD className="text-right tabular-nums text-muted-foreground">{e.retryCount}</TD>
                  <TD className="text-muted-foreground">{formatDateTime(e.createdAt)}</TD>
                  <TD className="text-muted-foreground">
                    {e.processedAt ? formatDateTime(e.processedAt) : "-"}
                  </TD>
                  <TD>
                    <div className="flex justify-end">
                      {(e.status === "dead" || e.status === "done") && (
                        <Can do={PERMISSIONS.eventsOperate}>
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={pending}
                            onClick={() => run(() => api.post(`/events/${e.id}/replay`), reload)}
                          >
                            Replay
                          </Button>
                        </Can>
                      )}
                    </div>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
        {data?.page && <Pagination page={data.page} onChange={setPage} label="events" />}
      </SectionCard>
    </div>
  );
}
