import { Button } from "./button";
import { Icon } from "@/components/Icon";

/** The paging envelope every list endpoint returns beside its rows. */
export interface PageInfo {
  page: number;
  pageSize: number;
  total: number;
  pages: number;
  hasMore: boolean;
}

/**
 * Previous/next control for a paged list.
 *
 * Renders nothing when everything fits on one page, so a small business never
 * sees paging chrome it has no use for.
 */
export function Pagination({
  page,
  onChange,
  label = "rows",
}: {
  page: PageInfo;
  onChange: (page: number) => void;
  label?: string;
}) {
  if (page.pages <= 1) return null;

  const first = (page.page - 1) * page.pageSize + 1;
  const last = Math.min(page.page * page.pageSize, page.total);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-5 py-3">
      <p className="text-sm text-muted-foreground">
        {first}–{last} of {page.total} {label}
      </p>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={page.page <= 1}
          onClick={() => onChange(page.page - 1)}
        >
          <Icon name="chevronRight" size={15} className="rotate-180" />
          Previous
        </Button>
        <span className="px-1 text-sm text-muted-foreground">
          Page {page.page} of {page.pages}
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={!page.hasMore}
          onClick={() => onChange(page.page + 1)}
        >
          Next
          <Icon name="chevronRight" size={15} />
        </Button>
      </div>
    </div>
  );
}
