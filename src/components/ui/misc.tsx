import * as React from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { Card } from "./card";

export function PageHeader({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-2xl font-bold tracking-[-0.035em] sm:text-[1.75rem]">{title}</h1>
        {description && <p className="mt-1.5 text-sm text-muted-foreground">{description}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}

export function StatCard({
  label,
  value,
  sub,
  icon,
  tone = "primary",
  href,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  icon?: React.ReactNode;
  tone?: "primary" | "success" | "warning" | "destructive" | "info";
  /** When set, the whole card becomes a link to this page. */
  href?: string;
}) {
  const toneBg: Record<string, string> = {
    primary: "bg-accent text-accent-foreground",
    success: "bg-success/15 text-success",
    warning: "bg-warning/15 text-warning",
    destructive: "bg-destructive/15 text-destructive",
    info: "bg-info/15 text-info",
  };
  const toneLine: Record<string, string> = {
    primary: "from-primary via-primary/70 to-primary/15",
    success: "from-success via-success/70 to-success/15",
    warning: "from-warning via-warning/70 to-warning/15",
    destructive: "from-destructive via-destructive/70 to-destructive/15",
    info: "from-info via-info/70 to-info/15",
  };
  const card = (
    <Card
      className={cn(
        "relative overflow-hidden p-5 sm:p-5",
        href &&
          "h-full transition-[box-shadow,border-color,transform] duration-150 group-hover:-translate-y-0.5 group-hover:border-foreground/20 group-hover:shadow-md",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-muted-foreground">{label}</p>
          <p className="mt-2 truncate text-2xl font-bold tracking-[-0.035em]">{value}</p>
          {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
        </div>
        {icon && (
          <span
            className={cn(
              "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl",
              toneBg[tone],
            )}
          >
            {icon}
          </span>
        )}
      </div>
      <div className={cn("mt-5 h-1 w-full rounded-full bg-gradient-to-r", toneLine[tone])} />
    </Card>
  );

  if (!href) return card;
  return (
    <Link href={href} className="group block rounded-xl focus-visible:focus-ring">
      {card}
    </Link>
  );
}

export function EmptyState({
  title,
  description,
  icon,
  action,
}: {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border bg-card/50 px-6 py-14 text-center">
      {icon && (
        <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
          {icon}
        </div>
      )}
      <p className="font-medium">{title}</p>
      {description && (
        <p className="mt-1 max-w-sm text-sm text-muted-foreground">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-muted", className)} />;
}

export function SectionCard({
  title,
  description,
  action,
  children,
  className,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Card className={className}>
      <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-4 sm:px-6">
        <div>
          <h3 className="font-semibold tracking-tight">{title}</h3>
          {description && <p className="text-sm text-muted-foreground">{description}</p>}
        </div>
        {action}
      </div>
      {children}
    </Card>
  );
}
