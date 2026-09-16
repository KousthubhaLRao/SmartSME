import { useEffect, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { cn, initials } from "@/lib/utils";
import { api, useApi } from "@/lib/api";
import { Icon, type IconName } from "./Icon";
import { BrandLockup, BrandMark } from "./Brand";
import { ThemeToggle } from "./ThemeToggle";
import { PERMISSIONS, useSession, type Permission } from "@/lib/session";

const COLLAPSE_KEY = "smartsme:sidebar-collapsed";
const WIDTH_KEY = "smartsme:sidebar-width";
const MIN_WIDTH = 190;
const MAX_WIDTH = 460;
const DEFAULT_WIDTH = 256;
const RAIL_WIDTH = 64;

/** How often the sidebar asks whether an order has arrived. Slower than the
 *  backend's own 30s collection sweep would be pointless, faster would cost a
 *  query for nothing; 20s means the badge is never more than one sweep behind. */
const INBOX_POLL_MS = 20_000;

/** `needs` hides the entry for roles without that permission. The API enforces
 *  the same rule, so this is about not offering a door that will not open. */
type NavItem = { to: string; label: string; icon: IconName; needs?: Permission };

const NAV: { label?: string; items: NavItem[] }[] = [
  {
    items: [
      { to: "/dashboard", label: "Dashboard", icon: "dashboard" },
      { to: "/input", label: "Smart Input", icon: "input", needs: PERMISSIONS.txnWrite },
      { to: "/inbox", label: "Inbox", icon: "bell" },
    ],
  },
  {
    label: "Operations",
    items: [
      { to: "/sales", label: "Sales", icon: "sales" },
      { to: "/purchases", label: "Purchases", icon: "purchases" },
      { to: "/products", label: "Products", icon: "products" },
      { to: "/parties", label: "Parties", icon: "parties" },
      { to: "/expenses", label: "Expenses", icon: "expenses" },
    ],
  },
  {
    label: "Insight & automation",
    items: [
      { to: "/reports", label: "Reports", icon: "reports" },
      { to: "/workflow", label: "Workflow", icon: "workflow", needs: PERMISSIONS.configWrite },
      { to: "/events", label: "Event bus", icon: "events" },
      { to: "/team", label: "Team", icon: "parties", needs: PERMISSIONS.usersManage },
    ],
  },
];

export function AppShell({
  businessName,
  userName,
  userEmail,
  onSwitchBusiness,
  children,
}: {
  businessName: string;
  userName: string;
  userEmail: string;
  /** Platform roles only: go back to the business picker. */
  onSwitchBusiness?: () => void;
  children: React.ReactNode;
}) {
  const { can, isPlatform, me } = useSession();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [width, setWidth] = useState(DEFAULT_WIDTH);
  const [dragging, setDragging] = useState(false);

  // The badge refreshes whenever the route changes, which is when new alerts
  // are most likely to have been raised by a write.
  const { data: unreadData } = useApi<{ unread: number }>(
    `/notifications/unread-count?at=${encodeURIComponent(location.pathname)}`,
  );
  const unread = unreadData?.unread ?? 0;

  // Orders that arrived by email or Telegram. The backend already collects
  // these on its own every 30s; without this nobody learns of one until they
  // open the Inbox and press Check now, which is not a notification, it is a
  // reminder to go looking. Polled on a slow clock from every page so the
  // count finds the person instead.
  const { data: inboxData, reload: reloadInbox } = useApi<{ pending: number }>(
    `/inbox/pending-count?at=${encodeURIComponent(location.pathname)}`,
  );
  const waiting = inboxData?.pending ?? 0;

  useEffect(() => {
    const id = setInterval(reloadInbox, INBOX_POLL_MS);
    // A tab left in the background can be throttled to a minute or more, so
    // refresh the moment it comes forward rather than trusting the timer.
    const onVisible = () => {
      if (document.visibilityState === "visible") reloadInbox();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [reloadInbox]);

  // The tab title too: the app is usually one of several tabs open, and a
  // count in the title is visible without switching to it.
  useEffect(() => {
    document.title = waiting > 0 ? `(${waiting}) SmartSME` : "SmartSME";
    // Signing out unmounts the shell; the count must not follow you to the
    // sign-in page, where it would be a number about nothing.
    return () => {
      document.title = "SmartSME";
    };
  }, [waiting]);

  useEffect(() => {
    try {
      if (localStorage.getItem(COLLAPSE_KEY) === "1") setCollapsed(true);
      const w = Number(localStorage.getItem(WIDTH_KEY));
      if (w >= MIN_WIDTH && w <= MAX_WIDTH) setWidth(w);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => setMobileOpen(false), [location.pathname]);

  function persist(key: string, value: string) {
    try {
      localStorage.setItem(key, value);
    } catch {
      /* ignore */
    }
  }

  // The edge handle is both a button and a drag handle: a plain click toggles
  // the icon-only rail; a horizontal drag sets an exact width.
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
        const next = !collapsed;
        setCollapsed(next);
        persist(COLLAPSE_KEY, next ? "1" : "0");
      } else {
        persist(COLLAPSE_KEY, "0");
        persist(WIDTH_KEY, String(lastWidth));
      }
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  async function signOut() {
    try {
      await api.post("/auth/sign-out");
    } finally {
      navigate("/sign-in", { replace: true });
    }
  }

  const navLink = (item: NavItem, mini: boolean) => {
    const count = item.to === "/inbox" ? waiting : 0;
    return (
      <NavLink
        key={item.to}
        to={item.to}
        title={mini ? item.label : undefined}
        aria-label={count > 0 ? `${item.label}, ${count} waiting` : mini ? item.label : undefined}
        className={({ isActive }) =>
          cn(
            "relative flex items-center gap-3 rounded-lg py-2 text-sm font-medium transition-colors",
            mini ? "justify-center px-0" : "px-3",
            isActive
              ? "bg-accent text-accent-foreground"
              : "text-muted-foreground hover:bg-muted hover:text-foreground",
          )
        }
      >
        <Icon name={item.icon} size={18} />
        {!mini && item.label}
        {count > 0 &&
          (mini ? (
            <span className="absolute right-2 top-1.5 h-2 w-2 rounded-full bg-destructive" />
          ) : (
            <span className="ml-auto flex h-5 min-w-5 items-center justify-center rounded-full bg-destructive px-1.5 text-[11px] font-semibold text-destructive-foreground">
              {count > 9 ? "9+" : count}
            </span>
          ))}
      </NavLink>
    );
  };

  // `mini` = the icon-only rail. The mobile drawer is always full-width.
  const sidebarInner = (mini: boolean) => (
    <>
      <div
        className={cn(
          "flex h-16 items-center border-b border-border",
          mini ? "justify-center px-2" : "px-4",
        )}
      >
        <Link
          to="/dashboard"
          aria-label="Go to dashboard"
          className="rounded-md transition-opacity hover:opacity-80 focus-visible:focus-ring"
        >
          {mini ? <BrandMark size={30} /> : <BrandLockup />}
        </Link>
      </div>

      <nav className="flex flex-1 flex-col gap-6 overflow-y-auto px-3 py-4">
        {NAV.map((group, gi) => {
          const items = group.items.filter((item) => !item.needs || can(item.needs));
          if (items.length === 0) return null;
          return (
            <div key={gi} className="flex flex-col gap-1">
              {group.label && !mini && (
                <div className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                  {group.label}
                </div>
              )}
              {items.map((item) => navLink(item, mini))}
            </div>
          );
        })}
      </nav>

      <div className="border-t border-border p-3">
        {navLink({ to: "/settings", label: "Settings", icon: "settings" }, mini)}
      </div>
    </>
  );

  return (
    <div
      className={cn("flex min-h-screen bg-background", dragging && "cursor-ew-resize select-none")}
    >
      {/* Desktop sidebar: resizable, and collapsible to an icon-only rail */}
      <aside
        style={{ width: collapsed ? RAIL_WIDTH : width }}
        className={cn(
          "sticky top-0 hidden h-screen shrink-0 flex-col border-r border-border bg-card lg:flex print:!hidden",
          !dragging && "transition-[width] duration-200 ease-out",
        )}
      >
        {sidebarInner(collapsed)}

        {/* Edge handle: click = collapse/expand, drag = set an exact width */}
        <button
          onMouseDown={onHandleMouseDown}
          aria-label="Resize sidebar, or click to collapse"
          title="Drag to resize · click to collapse"
          className="group absolute right-0 top-1/2 z-20 hidden h-12 w-4 -translate-y-1/2 translate-x-1/2 cursor-ew-resize items-center justify-center rounded-full border border-border bg-card shadow-sm hover:border-link/40 lg:flex"
        >
          <span className="h-5 w-[3px] rounded-full bg-border transition-colors group-hover:bg-link" />
        </button>
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden print:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={() => setMobileOpen(false)} />
          <aside className="absolute left-0 top-0 flex h-full w-64 flex-col border-r border-border bg-card">
            {sidebarInner(false)}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-border bg-card/80 px-4 backdrop-blur sm:px-6 print:hidden">
          <button
            onClick={() => setMobileOpen(true)}
            className="inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground hover:bg-muted lg:hidden"
            aria-label="Open menu"
          >
            <Icon name="menu" size={20} />
          </button>
          <div className="flex min-w-0 items-center gap-2">
            <Icon name="building" size={16} className="text-muted-foreground" />
            <span className="truncate text-sm font-medium">{businessName}</span>
            {isPlatform && (
              <button
                onClick={onSwitchBusiness}
                className="ml-1 rounded-md px-2 py-1 text-xs font-semibold text-link hover:bg-muted"
              >
                Switch
              </button>
            )}
          </div>

          <div className="ml-auto flex items-center gap-1">
            <Link
              to="/notifications"
              className="relative inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
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
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent text-xs font-semibold text-accent-foreground">
                {initials(userName)}
              </span>
              <div className="hidden leading-tight sm:block">
                <div className="text-sm font-medium">{userName}</div>
                <div className="text-[11px] text-muted-foreground">{userEmail}</div>
                <div className="text-[11px] font-medium text-link">{me.user.roleLabel}</div>
              </div>
              <button
                onClick={signOut}
                aria-label="Sign out"
                className="inline-flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <Icon name="logout" size={18} />
              </button>
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 lg:px-8">
          {children}
        </main>
      </div>
    </div>
  );
}
