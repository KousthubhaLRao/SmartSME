import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { api, isUnauthorized } from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { Skeleton } from "@/components/ui/misc";

import { SignIn } from "@/pages/SignIn";
import { SignUp } from "@/pages/SignUp";
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

export interface Me {
  user: { id: string; name: string; email: string; role: string };
  business: {
    id: string;
    name: string;
    currency: string;
    taxRate: number;
    invoicePrefix: string;
    gstNumber: string | null;
    panNumber: string | null;
    address: string | null;
    phone: string | null;
    email: string | null;
  };
}

export function App() {
  const location = useLocation();
  const [me, setMe] = useState<Me | null>(null);
  const [checked, setChecked] = useState(false);

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

  const isAuthRoute = location.pathname === "/sign-in" || location.pathname === "/sign-up";

  if (!checked && !isAuthRoute) {
    return (
      <div className="mx-auto max-w-5xl space-y-4 p-8">
        <Skeleton className="h-10 w-56" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (isAuthRoute) {
    return (
      <Routes>
        <Route path="/sign-in" element={<SignIn />} />
        <Route path="/sign-up" element={<SignUp />} />
      </Routes>
    );
  }

  if (!me) return <Navigate to="/sign-in" replace />;

  return (
    <AppShell businessName={me.business.name} userName={me.user.name} userEmail={me.user.email}>
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
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </AppShell>
  );
}
