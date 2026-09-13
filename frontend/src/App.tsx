import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { api, getActiveBusiness, isUnauthorized, setActiveBusiness } from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { Skeleton } from "@/components/ui/misc";
import { PERMISSIONS, SessionProvider, type Me, type Permission } from "@/lib/session";

import { SignIn } from "@/pages/SignIn";
import { SignUp } from "@/pages/SignUp";
import { Join } from "@/pages/Join";
import { PickBusiness } from "@/pages/PickBusiness";
import { Dashboard } from "@/pages/Dashboard";
import { SmartInput } from "@/pages/SmartInput";
import { Sales } from "@/pages/Sales";
import { SaleInvoice } from "@/pages/SaleInvoice";
import { Purchases } from "@/pages/Purchases";
import { Products } from "@/pages/Products";
import { Parties } from "@/pages/Parties";
import { Expenses } from "@/pages/Expenses";
import { Reports } from "@/pages/Reports";
import { Workflow } from "@/pages/Workflow";
import { Events } from "@/pages/Events";
import { Notifications } from "@/pages/Notifications";
import { Settings } from "@/pages/Settings";
import { Team } from "@/pages/Team";

export type { Me } from "@/lib/session";

/** Routes an employee or admin must not reach even by typing the URL. The API
 *  refuses them too; this only keeps the redirect tidy. */
const GUARDED: Record<string, Permission> = {
  "/input": PERMISSIONS.txnWrite,
  "/workflow": PERMISSIONS.configWrite,
  "/team": PERMISSIONS.usersManage,
};

export function App() {
  const location = useLocation();
  const [me, setMe] = useState<Me | null>(null);
  const [checked, setChecked] = useState(false);
  const [businessId, setBusinessId] = useState<string | null>(getActiveBusiness());

  // One session probe on mount; re-run when arriving from the auth pages.
  useEffect(() => {
    let alive = true;
    api
      .get<Me>("/auth/me")
      .then((res) => alive && setMe(res))
      .catch((e) => {
        if (alive && !isUnauthorized(e)) console.error(e);
        if (alive) setMe(null);
      })
      .finally(() => alive && setChecked(true));
    return () => {
      alive = false;
    };
  }, []);

  const isPublicRoute =
    location.pathname === "/sign-in" ||
    location.pathname === "/sign-up" ||
    location.pathname.startsWith("/join/");

  if (!checked && !isPublicRoute) {
    return (
      <div className="mx-auto max-w-5xl space-y-4 p-8">
        <Skeleton className="h-10 w-56" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (isPublicRoute) {
    return (
      <Routes>
        <Route path="/sign-in" element={<SignIn />} />
        <Route path="/sign-up" element={<SignUp />} />
        <Route path="/join/:token" element={<Join />} />
      </Routes>
    );
  }

  if (!me) return <Navigate to="/sign-in" replace />;

  const isPlatform = me.permissions.includes(PERMISSIONS.crossTenant);

  // A superuser or admin has no business of their own, so they pick one before
  // any tenant page has anything to show.
  if (isPlatform && !businessId) {
    return (
      <SessionProvider me={me}>
        <PickBusiness onPick={setBusinessId} />
      </SessionProvider>
    );
  }

  const needed = GUARDED[location.pathname];
  if (needed && !me.permissions.includes(needed)) {
    return <Navigate to="/dashboard" replace />;
  }

  function switchBusiness() {
    setActiveBusiness(null);
    setBusinessId(null);
  }

  return (
    <SessionProvider me={me}>
      <AppShell
        // A platform role's own `business` is null; the picked one names itself
        // on each page load, so fall back until the first response arrives.
        businessName={me.business?.name ?? "Select a business"}
        userName={me.user.name}
        userEmail={me.user.email}
        onSwitchBusiness={isPlatform ? switchBusiness : undefined}
      >
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/input" element={<SmartInput />} />
          <Route path="/sales" element={<Sales />} />
          <Route path="/sales/:id" element={<SaleInvoice />} />
          <Route path="/purchases" element={<Purchases />} />
          <Route path="/products" element={<Products />} />
          <Route path="/parties" element={<Parties />} />
          <Route path="/expenses" element={<Expenses />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/workflow" element={<Workflow />} />
          <Route path="/events" element={<Events />} />
          <Route path="/notifications" element={<Notifications />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/team" element={<Team />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </AppShell>
    </SessionProvider>
  );
}
