import { useState } from "react";
import { api, useApi, useMutation } from "@/lib/api";
import { PageHeader, PageState, EmptyState, SectionCard } from "@/components/ui/misc";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Pagination, type PageInfo } from "@/components/ui/pagination";
import { Icon } from "@/components/Icon";
import { cn, timeAgo } from "@/lib/utils";

interface Row {
  id: string;
  type: string;
  severity: string;
  title: string;
  message: string;
  read: boolean;
  createdAt: string;
}

const TONE: Record<string, "info" | "success" | "warning" | "destructive"> = {
  info: "info",
  success: "success",
  warning: "warning",
  error: "destructive",
};

export function Notifications() {
  const [page, setPage] = useState(1);
  const { data, loading, error, reload } = useApi<{
    rows: Row[];
    page: PageInfo;
    unread: number;
  }>(`/notifications?page=${page}`);
  const { run, pending } = useMutation();

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
      </PageHeader>

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
                  <p className="mt-1 text-xs text-muted-foreground">{timeAgo(n.createdAt)}</p>
                </div>
                {!n.read && (
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={pending}
                    onClick={() => run(() => api.post(`/notifications/${n.id}/read`), reload)}
                  >
                    Mark read
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
        {data?.page && <Pagination page={data.page} onChange={setPage} label="notifications" />}
      </SectionCard>
    </div>
  );
}
