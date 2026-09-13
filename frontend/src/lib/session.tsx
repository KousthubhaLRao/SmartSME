/**
 * Who is signed in, and what they are allowed to do.
 *
 * The permission list comes from the server with the session — the client never
 * derives it from the role name, so the two can never drift. This is for
 * *hiding* things only: every rule is enforced again on the API, and the UI
 * gating is a courtesy so nobody clicks a button that will 403.
 */
import { createContext, useContext, type ReactNode } from "react";

export const PERMISSIONS = {
  dataRead: "data:read",
  txnWrite: "txn:write",
  dataManage: "data:manage",
  catalogWrite: "catalog:write",
  configWrite: "config:write",
  usersManage: "users:manage",
  eventsOperate: "events:operate",
  crossTenant: "platform:cross-tenant",
} as const;

export type Permission = (typeof PERMISSIONS)[keyof typeof PERMISSIONS];

export interface SessionUser {
  id: string;
  name: string;
  email: string;
  role: string;
  roleLabel: string;
}

export interface SessionBusiness {
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
}

export interface Me {
  user: SessionUser;
  permissions: string[];
  /** Null for a platform role, which belongs to no business of its own. */
  business: SessionBusiness | null;
}

interface SessionValue {
  me: Me;
  can: (permission: Permission) => boolean;
  isPlatform: boolean;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ me, children }: { me: Me; children: ReactNode }) {
  const value: SessionValue = {
    me,
    can: (permission) => me.permissions.includes(permission),
    isPlatform: me.permissions.includes(PERMISSIONS.crossTenant),
  };
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside a SessionProvider");
  return ctx;
}

/** Shorthand for the common case of gating one element. */
export function useCan(): (permission: Permission) => boolean {
  return useSession().can;
}

/** Renders its children only when the session holds the permission. */
export function Can({ do: permission, children }: { do: Permission; children: ReactNode }) {
  return useCan()(permission) ? <>{children}</> : null;
}
