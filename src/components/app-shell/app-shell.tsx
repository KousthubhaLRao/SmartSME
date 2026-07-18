"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn, initials } from "@/lib/utils";
import { Icon, type IconName } from "@/components/icons";
import { BrandLockup, BrandMark } from "@/components/brand";
import { ThemeToggle } from "@/components/theme-toggle";
import { signOutAction } from "@/lib/auth/actions";

const COLLAPSE_KEY = "smartsme:sidebar-collapsed";
const WIDTH_KEY = "smartsme:sidebar-width";
const MIN_WIDTH = 190;
const MAX_WIDTH = 460;
const DEFAULT_WIDTH = 242;
const RAIL_WIDTH = 64;

type NavItem = { href: string; label: string; icon: IconName };
type NavGroup = { label?: string; items: NavItem[] };

const NAV: NavGroup[] = [
  {
    items: [
      { href: "/dashboard", label: "Dashboard", icon: "dashboard" },
      { href: "/input", label: "Smart Input", icon: "input" },
    ],
  },
  {
    label: "Operations",
    items: [
      { href: "/sales", label: "Sales", icon: "sales" },
      { href: "/purchases", label: "Purchases", icon: "purchases" },
      { href: "/products", label: "Products", icon: "products" },
      { href: "/parties", label: "Parties", icon: "parties" },
      { href: "/expenses", label: "Expenses", icon: "expenses" },
    ],
  },
  {
    label: "Insight & automation",
    items: [
      { href: "/reports", label: "Reports", icon: "reports" },
      { href: "/workflow", label: "Workflow", icon: "workflow" },
      { href: "/events", label: "Event bus", icon: "events" },
    ],
  },
];

export function AppShell({
  businessName,
  userName,
  userEmail,
  unread,
  children,
}: {
  businessName: string;
  userName: string;
  userEmail: string;
  unread: number;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  const [dragging, setDragging] = useState(false);

  // Restore the collapsed/width preferences (desktop only) across reloads.
  useEffect(() => {
    try {
      if (localStorage.getItem(COLLAPSE_KEY) === "1") setCollapsed(true);
      const w = Number(localStorage.getItem(WIDTH_KEY));
      if (w >= MIN_WIDTH && w <= MAX_WIDTH) setWidth(w);
    } catch {
      /* ignore */
    }
  }, []);

  function persist(key: string, value: string) {
    try {
      localStorage.setItem(key, value);
    } catch {
      /* ignore */
    }
  }

  function setCollapsedPersisted(next: boolean) {
    setCollapsed(next);
    persist(COLLAPSE_KEY, next ? "1" : "0");
  }

  // The edge handle is both a button and a drag handle: a plain click toggles the
  // icon-only rail; a horizontal drag sets an exact width the page flexes around.
  function onHandleMouseDown(e: React.MouseEvent) {
    e.preventDefault();
    const startX = e.clientX;
    let moved = false;
    let lastWidth = width;
    setDragging(true);

    const onMove = (ev: MouseEvent) => {
      if (!moved && Math.abs(ev.clientX - startX) > 4) moved = true;
      if (!moved) return;
      lastWidth = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, ev.clientX));
      setCollapsed(false);
      setWidth(lastWidth);
    };
    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      setDragging(false);
      if (!moved) {
        setCollapsedPersisted(!collapsed); // treat as a click
      } else {
        persist(COLLAPSE_KEY, "0");
        persist(WIDTH_KEY, String(lastWidth));
      }
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  const isActive = (href: string) => pathname === href || pathname.startsWith(href + "/");

  const navLink = (href: string, label: string, icon: IconName, mini: boolean) => (
    <Link
      key={href}
      href={href}
      onClick={() => setMobileOpen(false)}
      title={mini ? label : undefined}
      aria-label={mini ? label : undefined}
      className={cn(
        "flex items-center gap-3 rounded-xl py-2.5 text-sm font-medium transition-[background-color,color,box-shadow]",
        mini ? "justify-center px-0" : "px-3",
        isActive(href)
          ? "bg-accent text-accent-foreground shadow-sm"
          : "text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      <Icon name={icon} size={18} />
      {!mini && label}
    </Link>
  );

  // `mini` = the icon-only rail. The mobile drawer is always full-width.
  const sidebarInner = (mini: boolean) => (
    <>
      <div
        className={cn(
          "flex h-20 items-center",
          mini ? "justify-center px-2" : "px-4",
        )}
      >
        <Link
          href="/dashboard"
          onClick={() => setMobileOpen(false)}
          aria-label="Go to dashboard"
          className="rounded-md transition-opacity hover:opacity-80 focus-visible:focus-ring"
        >
          {mini ? <BrandMark size={30} /> : <BrandLockup />}
        </Link>
      </div>

      <nav className="flex flex-1 flex-col gap-6 overflow-y-auto px-3 py-5">
        {NAV.map((group, gi) => (
          <div key={gi} className="flex flex-col gap-1">
            {group.label && !mini && (
              <div className="px-3 pb-1 text-[10px] font-bold uppercase tracking-[0.08em] text-muted-foreground/70">
                {group.label}
              </div>
            )}
            {group.items.map((item) => navLink(item.href, item.label, item.icon, mini))}
          </div>
        ))}
      </nav>

      {!mini && (
        <div className="mx-3 mb-4 rounded-2xl border border-primary/15 bg-[linear-gradient(145deg,color-mix(in_oklab,var(--primary)_15%,var(--card)),var(--card))] p-4">
          <p className="text-sm font-semibold">Grow your business</p>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">Use Smart Input to turn everyday notes into records.</p>
          <Link href="/input" className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline">
            Explore Smart Input <Icon name="chevronRight" size={14} />
          </Link>
        </div>
      )}
      <div className="border-t border-border p-3">{navLink("/settings", "Settings", "settings", mini)}</div>
    </>
  );

  return (
    <div className={cn("flex min-h-screen bg-background", dragging && "cursor-ew-resize select-none")}>
      {/* Desktop sidebar — resizable, and collapsible to an icon-only rail */}
      <aside
        style={{ width: collapsed ? RAIL_WIDTH : width }}
        className={cn(
          "sticky top-0 hidden h-screen shrink-0 flex-col border-r border-border/80 bg-card/90 backdrop-blur-xl lg:flex",
          !dragging && "transition-[width] duration-200 ease-out",
        )}
      >
        {sidebarInner(collapsed)}

        {/* Edge handle: click = collapse/expand, drag = set an exact width */}
        <button
          onMouseDown={onHandleMouseDown}
          aria-label="Resize sidebar, or click to collapse"
          title="Drag to resize · click to collapse"
          className="group absolute right-0 top-1/2 z-20 hidden h-12 w-4 -translate-y-1/2 translate-x-1/2 cursor-ew-resize items-center justify-center rounded-full border border-border bg-card shadow-sm hover:border-primary/40 lg:flex"
        >
          <span className="h-5 w-[3px] rounded-full bg-border transition-colors group-hover:bg-primary" />
        </button>
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={() => setMobileOpen(false)} />
          <aside className="absolute left-0 top-0 flex h-full w-64 flex-col border-r border-border bg-card">
            {sidebarInner(false)}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Topbar */}
        <header className="sticky top-0 z-30 flex h-20 items-center gap-3 border-b border-border/70 bg-background/75 px-4 backdrop-blur-xl sm:px-6 lg:px-8">
          <button
            onClick={() => setMobileOpen(true)}
            className="inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground hover:bg-muted lg:hidden"
            aria-label="Open menu"
          >
            <Icon name="menu" size={20} />
          </button>
          <div className="hidden min-w-0 lg:block">
            <p className="text-lg font-bold tracking-[-0.03em]">Welcome back, {userName.split(" ")[0]}!</p>
            <p className="mt-0.5 text-xs text-muted-foreground">Here&apos;s what&apos;s happening with {businessName} today.</p>
          </div>

          <div className="ml-auto flex items-center gap-2">
            <label className="hidden h-11 w-72 items-center gap-2 rounded-xl border border-border bg-card px-3 text-muted-foreground shadow-sm xl:flex">
              <Icon name="search" size={18} />
              <input aria-label="Search" placeholder="Search anything..." className="min-w-0 flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground" />
              <kbd className="rounded-md bg-muted px-1.5 py-0.5 text-[10px] font-semibold">⌘ K</kbd>
            </label>
            <Link
              href="/notifications"
              className="relative inline-flex h-10 w-10 items-center justify-center rounded-xl text-muted-foreground hover:bg-muted hover:text-foreground"
              aria-label="Notifications"
            >
              <Icon name="bell" size={18} />
              {unread > 0 && (
                <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold text-destructive-foreground">
                  {unread > 9 ? "9+" : unread}
                </span>
              )}
            </Link>
            <ThemeToggle />
            <div className="ml-1 flex items-center gap-2 border-l border-border pl-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-accent text-xs font-bold text-accent-foreground">
                {initials(userName)}
              </span>
              <div className="hidden leading-tight sm:block">
                <div className="text-sm font-medium">{userName}</div>
                <div className="text-[11px] text-muted-foreground">{userEmail}</div>
              </div>
              <form action={signOutAction}>
                <button
                  type="submit"
                  aria-label="Sign out"
                  className="inline-flex h-10 w-10 items-center justify-center rounded-xl text-muted-foreground hover:bg-muted hover:text-foreground"
                >
                  <Icon name="logout" size={18} />
                </button>
              </form>
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-6 sm:px-6 lg:px-8">
          {children}
        </main>
      </div>
    </div>
  );
}
