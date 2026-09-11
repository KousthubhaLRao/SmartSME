import { useState } from "react";
import { Link } from "react-router-dom";
import { api, useMutation } from "@/lib/api";
import { AuthLayout } from "@/components/AuthLayout";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";

const DEMO = { email: "demo@smartsme.app", password: "demo1234" };

export function SignIn() {
  const { run, pending, error } = useMutation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  function signIn(credentials: typeof DEMO) {
    return run(
      () => api.post("/auth/sign-in", credentials),
      // A full load re-runs the session probe in App with the new cookie.
      () => window.location.assign("/dashboard"),
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    await signIn({ email, password });
  }

  async function useDemo() {
    setEmail(DEMO.email);
    setPassword(DEMO.password);
    await signIn(DEMO);
  }

  return (
    <AuthLayout>
      <h1 className="text-[1.75rem] font-bold tracking-[-0.03em]">Welcome back</h1>
      <p className="mt-2 text-sm text-muted-foreground">Sign in to your SmartSME workspace.</p>

      <form onSubmit={submit} className="mt-8 flex flex-col gap-4">
        <Field label="Email">
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@business.com"
            autoComplete="email"
            required
          />
        </Field>
        <Field label="Password">
          <Input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            autoComplete="current-password"
            required
          />
        </Field>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Button type="submit" size="lg" className="mt-2 w-full" disabled={pending}>
          {pending ? "Signing in…" : "Sign in"}
        </Button>
      </form>

      <button
        type="button"
        onClick={useDemo}
        disabled={pending}
        className="mt-4 w-full rounded-lg py-1 text-sm font-semibold text-link transition-opacity hover:opacity-70 focus-visible:focus-ring disabled:opacity-50"
      >
        Use the demo account
      </button>

      <p className="mt-6 text-center text-sm text-muted-foreground">
        New here?{" "}
        <Link to="/sign-up" className="font-semibold text-link hover:underline">
          Create an account
        </Link>
      </p>
    </AuthLayout>
  );
}
