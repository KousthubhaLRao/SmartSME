/**
 * Tiny API client + data hooks.
 *
 * Every request sends the session cookie (`credentials: "include"`). A 401 is
 * surfaced as `Unauthorized`, which the router turns into a redirect to
 * sign-in. Deliberately dependency-free: the app is almost entirely
 * "load a page, mutate, reload", so a data-fetching library would be overkill.
 */
import { useCallback, useEffect, useRef, useState } from "react";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export const isUnauthorized = (e: unknown) => e instanceof ApiError && e.status === 401;
export const isForbidden = (e: unknown) => e instanceof ApiError && e.status === 403;

/**
 * The business a superuser or admin is currently looking at.
 *
 * Platform accounts belong to no business, so the API needs to be told which
 * one every tenant request is for. Keeping it here means the page components
 * never have to thread it through. It stays null for owners and employees,
 * who are pinned to their own business server-side.
 */
const ACTIVE_BUSINESS_KEY = "smartsme-active-business";
let activeBusinessId: string | null = null;

export function setActiveBusiness(id: string | null) {
  activeBusinessId = id;
  try {
    if (id) localStorage.setItem(ACTIVE_BUSINESS_KEY, id);
    else localStorage.removeItem(ACTIVE_BUSINESS_KEY);
  } catch {
    /* private browsing: the choice just will not survive a reload */
  }
}

export function getActiveBusiness(): string | null {
  if (activeBusinessId) return activeBusinessId;
  try {
    activeBusinessId = localStorage.getItem(ACTIVE_BUSINESS_KEY);
  } catch {
    activeBusinessId = null;
  }
  return activeBusinessId;
}

function withBusiness(path: string): string {
  const id = getActiveBusiness();
  if (!id || path.startsWith("/auth/") || path.startsWith("/businesses")) return path;
  return `${path}${path.includes("?") ? "&" : "?"}businessId=${encodeURIComponent(id)}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = withBusiness(path);
  const res = await fetch(url.startsWith("/api") ? url : `/api${url}`, {
    credentials: "include",
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    ...init,
  });

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
      // FastAPI validation errors arrive as a list of issues.
      else if (Array.isArray(body?.detail))
        detail = body.detail.map((d: { msg: string }) => d.msg).join(", ");
    } catch {
      /* keep the generic message */
    }
    throw new ApiError(detail, res.status);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "PUT",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "PATCH",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<T>(path, { method: "POST", body: form });
  },
  /** Streams a file download (report PDF/CSV) straight to the browser. */
  download: async (path: string) => {
    const target = withBusiness(path);
    const res = await fetch(target.startsWith("/api") ? target : `/api${target}`, {
      credentials: "include",
    });
    if (!res.ok) {
      let detail = `Download failed (${res.status})`;
      try {
        const body = await res.json();
        if (typeof body?.detail === "string") detail = body.detail;
      } catch {
        /* keep the generic message */
      }
      throw new ApiError(detail, res.status);
    }
    const blob = await res.blob();
    const name =
      /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "")?.[1] ?? "report";
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    return name;
  },
};

export interface QueryState<T> {
  data: T | undefined;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

/** Loads `path` on mount and exposes a `reload` for after mutations. */
export function useApi<T>(path: string | null): QueryState<T> {
  const [data, setData] = useState<T | undefined>(undefined);
  const [loading, setLoading] = useState(path !== null);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  // Guards against a late response from a previous path overwriting the new one.
  const latest = useRef(0);

  useEffect(() => {
    if (path === null) {
      setLoading(false);
      return;
    }
    const ticket = ++latest.current;
    setLoading(true);
    setError(null);
    api
      .get<T>(path)
      .then((res) => {
        if (ticket === latest.current) setData(res);
      })
      .catch((e: unknown) => {
        if (ticket !== latest.current) return;
        if (isUnauthorized(e)) {
          window.location.assign("/sign-in");
          return;
        }
        setError(e instanceof Error ? e.message : "Something went wrong.");
      })
      .finally(() => {
        if (ticket === latest.current) setLoading(false);
      });
  }, [path, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { data, loading, error, reload };
}

/** Wraps a mutation with pending/error state and an optional success callback. */
export function useMutation() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async <T>(fn: () => Promise<T>, onDone?: (result: T) => void) => {
    setPending(true);
    setError(null);
    try {
      const result = await fn();
      onDone?.(result);
      return true;
    } catch (e) {
      if (isUnauthorized(e)) {
        window.location.assign("/sign-in");
        return false;
      }
      setError(e instanceof Error ? e.message : "Something went wrong.");
      return false;
    } finally {
      setPending(false);
    }
  }, []);

  return { run, pending, error, setError };
}
