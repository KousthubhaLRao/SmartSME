import { useState } from "react";
import { Link } from "react-router-dom";
import { api, useMutation } from "@/lib/api";
import { AuthLayout } from "@/components/AuthLayout";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";

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
    <AuthLayout>
      <h1 className="text-[1.75rem] font-bold tracking-[-0.03em]">Create your account</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Your business starts with the default workflow rules.
      </p>

      <form onSubmit={submit} className="mt-8 flex flex-col gap-4">
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
            placeholder="you@business.com"
            autoComplete="email"
            required
          />
        </Field>
        <Field label="Password" hint="At least 6 characters.">
          <Input
            type="password"
            value={form.password}
            onChange={set("password")}
            placeholder="••••••••"
            autoComplete="new-password"
            minLength={6}
            required
          />
        </Field>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Button type="submit" size="lg" className="mt-2 w-full" disabled={pending}>
          {pending ? "Creating…" : "Create account"}
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link to="/sign-in" className="font-semibold text-link hover:underline">
          Sign in
        </Link>
      </p>
    </AuthLayout>
  );
}
