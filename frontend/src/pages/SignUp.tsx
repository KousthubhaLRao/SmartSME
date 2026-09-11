import { useState } from "react";
import { Link } from "react-router-dom";
import { api, useMutation } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/input";
import { BrandLockup } from "@/components/Brand";

export function SignUp() {
  const { run, pending, error } = useMutation();
  const [form, setForm] = useState({ businessName: "", name: "", email: "", password: "" });

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    await run(
      () => api.post("/auth/sign-up", form),
      () => window.location.assign("/dashboard"),
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex justify-center">
          <BrandLockup />
        </div>
        <Card className="p-6">
          <h1 className="text-lg font-semibold tracking-tight">Create your account</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Your business starts with the default workflow rules.
          </p>

          <form onSubmit={submit} className="mt-5 flex flex-col gap-4">
            <Field label="Business name">
              <Input
                value={form.businessName}
                onChange={set("businessName")}
                placeholder="Kirana Fresh Traders"
                required
              />
            </Field>
            <Field label="Your name">
              <Input value={form.name} onChange={set("name")} placeholder="Owner name" required />
            </Field>
            <Field label="Email">
              <Input
                type="email"
                value={form.email}
                onChange={set("email")}
                autoComplete="email"
                required
              />
            </Field>
            <Field label="Password" hint="At least 6 characters.">
              <Input
                type="password"
                value={form.password}
                onChange={set("password")}
                autoComplete="new-password"
                minLength={6}
                required
              />
            </Field>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" disabled={pending}>
              {pending ? "Creating…" : "Create account"}
            </Button>
          </form>

          <p className="mt-4 text-center text-sm text-muted-foreground">
            Already have an account?{" "}
            <Link to="/sign-in" className="text-primary hover:underline">
              Sign in
            </Link>
          </p>
        </Card>
      </div>
    </div>
  );
}
