import { useState } from "react";
import { api, useApi, useMutation } from "@/lib/api";
import { PageHeader, PageState, EmptyState, SectionCard } from "@/components/ui/misc";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Pagination, type PageInfo } from "@/components/ui/pagination";
import { Icon } from "@/components/Icon";
import { Can, PERMISSIONS, useCan } from "@/lib/session";
import { cn, timeAgo } from "@/lib/utils";

interface Row {
  id: string;
  type: string;
  severity: string;
  title: string;
  message: string;
  read: boolean;
  eventId: string | null;
  ruleId: string | null;
  /** What raised it: which rule, on which event, and who caused that event. */
  source: { rule: string | null; eventType: string | null; actor: string | null } | null;
  createdAt: string;
}

interface SeverityCount {
  value: string;
  count: number;
}

const TONE: Record<string, "info" | "success" | "warning" | "destructive"> = {
  info: "info",
  success: "success",
  warning: "warning",
  error: "destructive",
};

export function Notifications() {
  const [page, setPage] = useState(1);
  const [severity, setSeverity] = useState("");
  const [unreadOnly, setUnreadOnly] = useState(false);
  const query = new URLSearchParams({ page: String(page) });
  if (severity) query.set("severity", severity);
  if (unreadOnly) query.set("unread", "true");
  const { data, loading, error, reload } = useApi<{
    rows: Row[];
    page: PageInfo;
    unread: number;
    severities: SeverityCount[];
  }>(`/notifications?${query}`);
  // `actionError` is shown, not swallowed. Dismissing and clearing need
  // `data:manage`, which an employee and an admin do not hold, so both used to
  // answer 403 into a void: the button clicked, the row stayed, and nothing on
  // the page ever said why.
  const { run, pending, error: actionError } = useMutation();
  const can = useCan();

  /** Changing a filter must go back to page one, or you land past the end. */
  function filter(next: { severity?: string; unread?: boolean }) {
    if (next.severity !== undefined) setSeverity(next.severity);
    if (next.unread !== undefined) setUnreadOnly(next.unread);
    setPage(1);
  }

  if (!data) return <PageState loading={loading} error={error} />;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Notifications"
        description={`${data.unread} unread alert${data.unread === 1 ? "" : "s"}.`}
      >
        {data.unread > 0 && (
          <Button
            variant="outline"
            disabled={pending}
            onClick={() => run(() => api.post("/notifications/read-all"), reload)}
          >
            <Icon name="check" size={16} /> Mark all read
          </Button>
        )}
        <Can do={PERMISSIONS.dataManage}>
          <Button
            variant="outline"
            disabled={pending}
            onClick={() => run(() => api.post("/notifications/clear-read"), reload)}
          >
            <Icon name="trash" size={16} /> Clear read
          </Button>
        </Can>
      </PageHeader>

      {actionError && (
        <p className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {actionError}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <FilterChip
          active={!severity && !unreadOnly}
          onClick={() => filter({ severity: "", unread: false })}
        >
          All
        </FilterChip>
        <FilterChip active={unreadOnly} onClick={() => filter({ unread: !unreadOnly })}>
          Unread ({data.unread})
        </FilterChip>
        {data.severities.map((s) => (
          <FilterChip
            key={s.value}
            active={severity === s.value}
            onClick={() => filter({ severity: severity === s.value ? "" : s.value })}
          >
            {s.value} ({s.count})
          </FilterChip>
        ))}
      </div>

      <SectionCard title="Alerts" description="Raised by the workflow engine">
        {data.rows.length === 0 ? (
          <div className="p-6">
            <EmptyState
              icon={<Icon name="bell" />}
              title="Nothing yet"
              description="Alerts appear here as events are processed."
            />
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {data.rows.map((n) => (
              <li
                key={n.id}
                className={cn("flex items-start gap-3 p-4", !n.read && "bg-accent/30")}
              >
                <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                  <Icon
                    name={n.severity === "error" || n.severity === "warning" ? "alert" : "bell"}
                    size={15}
                  />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{n.title}</span>
                    <Badge tone={TONE[n.severity] ?? "info"}>{n.severity}</Badge>
                    {!n.read && <Badge tone="primary">New</Badge>}
                  </div>
                  <p className="mt-0.5 text-sm text-muted-foreground">{n.message}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {timeAgo(n.createdAt)}
                    {n.source?.rule && <> · rule {n.source.rule}</>}
                    {n.source?.eventType && <> · {n.source.eventType}</>}
                    {n.source?.actor && <> · by {n.source.actor}</>}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={pending}
                    onClick={() =>
                      run(
                        () => api.post(`/notifications/${n.id}/${n.read ? "unread" : "read"}`),
                        reload,
                      )
                    }
                  >
                    {n.read ? "Unread" : "Mark read"}
                  </Button>
                  {can(PERMISSIONS.dataManage) && (
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label="Dismiss"
                      disabled={pending}
                      onClick={() => run(() => api.del(`/notifications/${n.id}`), reload)}
                    >
                      <Icon name="x" size={15} />
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
        {data?.page && <Pagination page={data.page} onChange={setPage} label="notifications" />}
      </SectionCard>
    </div>
  );
}

function FilterChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full border px-3 py-1 text-xs font-medium capitalize transition-colors focus-visible:focus-ring",
        active
          ? "border-transparent bg-accent text-accent-foreground"
          : "border-border text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}
