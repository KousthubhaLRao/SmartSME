import { api, setActiveBusiness, useApi } from "@/lib/api";
import { PageState, EmptyState } from "@/components/ui/misc";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { BrandLockup } from "@/components/Brand";
import { Icon } from "@/components/Icon";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useSession } from "@/lib/session";

interface BusinessRow {
  id: string;
  name: string;
  currency: string;
  taxRate: number;
  members: number;
  sales: number;
  createdAt: string;
}

/**
 * Where a superuser or admin lands. They belong to no business, so they have to
 * pick one before any tenant page has anything to show; the choice is kept in
 * `lib/api` and sent as `?businessId=` on every later request.
 */
export function PickBusiness({ onPick }: { onPick: (id: string) => void }) {
  const { data, loading, error } = useApi<{ rows: BusinessRow[] }>("/businesses");
  const { me } = useSession();

  function pick(id: string) {
    setActiveBusiness(id);
    onPick(id);
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-4xl flex-col gap-8 px-6 py-12">
      <div className="flex items-start justify-between gap-4">
        <BrandLockup />
        <div className="flex items-center gap-2">
          <Badge tone="primary">{me.user.roleLabel}</Badge>
          <ThemeToggle />
          <button
            onClick={() =>
              api.post("/auth/sign-out").then(() => window.location.assign("/sign-in"))
            }
            className="inline-flex h-9 w-9 items-center justify-center rounded-xl text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label="Sign out"
          >
            <Icon name="logout" size={18} />
          </button>
        </div>
      </div>

      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Choose a business</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Your account is not tied to one business. Pick the one you want to work in — you can
          switch at any time from the sidebar.
        </p>
      </div>

      <PageState loading={loading} error={error} />

      {data &&
        (data.rows.length === 0 ? (
          <EmptyState
            title="No businesses yet"
            description="Nobody has signed up on this instance."
          />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {data.rows.map((b) => (
              <button key={b.id} onClick={() => pick(b.id)} className="text-left">
                <Card className="p-5 transition-shadow hover:shadow-lg">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate font-semibold tracking-tight">{b.name}</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {b.members} member{b.members === 1 ? "" : "s"} · {b.sales} sale
                        {b.sales === 1 ? "" : "s"} · {b.currency} · {b.taxRate}% tax
                      </p>
                    </div>
                    <Icon name="chevronRight" size={16} className="mt-1 shrink-0 text-link" />
                  </div>
                </Card>
              </button>
            ))}
          </div>
        ))}
    </div>
  );
}
