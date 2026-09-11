import { useState } from "react";
import { Link } from "react-router-dom";
import { api, useMutation } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/input";
import { BrandLockup } from "@/components/Brand";

export function SignIn() {
  const { run, pending, error } = useMutation();
  const [email, setEmail] = useState("demo@smartsme.app");
  const [password, setPassword] = useState("demo1234");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    await run(
      () => api.post("/auth/sign-in", { email, password }),
      // A full load re-runs the session probe in App with the new cookie.
      () => window.location.assign("/dashboard"),
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex justify-center">
          <BrandLockup />
        </div>
        <Card className="p-6">
          <h1 className="text-lg font-semibold tracking-tight">Sign in</h1>
          <p className="mt-1 text-sm text-muted-foreground">Welcome back to your business.</p>

          <form onSubmit={submit} className="mt-5 flex flex-col gap-4">
            <Field label="Email">
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
              />
            </Field>
            <Field label="Password">
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </Field>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" disabled={pending}>
              {pending ? "Signing in…" : "Sign in"}
            </Button>
          </form>

          <p className="mt-4 text-center text-sm text-muted-foreground">
            No account?{" "}
            <Link to="/sign-up" className="text-primary hover:underline">
              Create one
            </Link>
          </p>
        </Card>
        <p className="mt-4 text-center text-xs text-muted-foreground">
          Demo login is pre-filled: demo@smartsme.app / demo1234
        </p>
      </div>
    </div>
  );
}
