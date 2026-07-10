import { eq } from "drizzle-orm";
import { db } from "@/db";
import * as sc from "@/db/schema";
import { requireUser } from "@/lib/auth/current-user";
import { hasAI, aiStatus } from "@/lib/ai/client";
import { PageHeader } from "@/components/ui/misc";
import { Card } from "@/components/ui/card";
import { Icon } from "@/components/icons";
import { InputConsole } from "./input-console";

export default async function InputPage() {
  const { business } = await requireUser();

  const parties = await db
    .select({ id: sc.parties.id, name: sc.parties.name, type: sc.parties.type })
    .from(sc.parties)
    .where(eq(sc.parties.businessId, business.id))
    .orderBy(sc.parties.name);

  const products = await db
    .select({
      id: sc.products.id,
      name: sc.products.name,
      unit: sc.products.unit,
      sellingPrice: sc.products.sellingPrice,
      purchasePrice: sc.products.purchasePrice,
    })
    .from(sc.products)
    .where(eq(sc.products.businessId, business.id))
    .orderBy(sc.products.name);

  const steps = [
    { icon: "input", label: "Type or snap" },
    { icon: "workflow", label: "AI extracts" },
    { icon: "check", label: "You confirm" },
    { icon: "events", label: "Event published" },
  ] as const;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Smart Input Engine"
        description="Turn plain language or a photo into structured business events. You approve before anything is published."
      />

      <Card className="p-4">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {steps.map((s, i) => (
            <div key={s.label} className="flex items-center gap-2">
              <span className="flex items-center gap-2 rounded-full bg-muted px-3 py-1.5 font-medium">
                <Icon name={s.icon} size={15} className="text-primary" />
                {s.label}
              </span>
              {i < steps.length - 1 && <Icon name="chevronRight" size={14} className="text-muted-foreground" />}
            </div>
          ))}
        </div>
      </Card>

      <InputConsole
        parties={parties}
        products={products}
        currency={business.currency}
        taxRate={business.taxRate}
        hasAI={hasAI()}
        aiLabel={aiStatus()?.label ?? null}
      />
    </div>
  );
}
