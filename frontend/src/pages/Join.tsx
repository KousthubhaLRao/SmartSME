import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, useMutation } from "@/lib/api";
import { AuthLayout } from "@/components/AuthLayout";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";

interface InvitePreview {
  email: string;
  role: string;
  roleLabel: string;
  businessName: string;
}

/** Accepting an invitation: the token in the link is the whole credential, so
 *  the invitee only picks a name and a password. */
export function Join() {
  const { token = "" } = useParams();
  const { run, pending, error } = useMutation();
  const [invite, setInvite] = useState<InvitePreview | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "invalid">("loading");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");

  useEffect(() => {
    let alive = true;
    api
      .get<InvitePreview>(`/auth/invite/${encodeURIComponent(token)}`)
      .then((res) => {
        if (!alive) return;
        setInvite(res);
        setState("ready");
      })
      .catch(() => alive && setState("invalid"));
    return () => {
      alive = false;
    };
  }, [token]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    await run(
      () => api.post("/auth/accept-invite", { token, name, password }),
      () => window.location.assign("/dashboard"),
    );
  }

  if (state === "loading") {
    return (
      <AuthLayout>
        <Skeleton className="h-8 w-48" />
        <Skeleton className="mt-4 h-4 w-64" />
        <Skeleton className="mt-8 h-32 w-full" />
      </AuthLayout>
    );
  }

  if (state === "invalid") {
    return (
      <AuthLayout>
        <h1 className="text-[1.75rem] font-bold tracking-[-0.03em]">Invitation expired</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          This link is no longer valid. Invitations last seven days and can only be used once — ask
          whoever invited you to send a new one.
        </p>
        <p className="mt-6 text-sm text-muted-foreground">
          Already have an account?{" "}
          <Link to="/sign-in" className="font-semibold text-link hover:underline">
            Sign in
          </Link>
        </p>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout>
      <h1 className="text-[1.75rem] font-bold tracking-[-0.03em]">Join {invite?.businessName}</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        You have been invited as {invite?.roleLabel.toLowerCase()}. Pick a password to finish
        setting up <span className="font-medium text-foreground">{invite?.email}</span>.
      </p>

      <form onSubmit={submit} className="mt-8 flex flex-col gap-4">
        <Field label="Your name">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Your name"
            required
          />
        </Field>
        <Field label="Password" hint="At least 6 characters.">
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            autoComplete="new-password"
            minLength={6}
            required
          />
        </Field>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Button type="submit" size="lg" className="mt-2 w-full" disabled={pending}>
          {pending ? "Joining…" : "Join the team"}
        </Button>
      </form>
    </AuthLayout>
  );
}
