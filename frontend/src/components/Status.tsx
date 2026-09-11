import { Badge } from "@/components/ui/badge";

export function PaymentBadge({ status }: { status: string }) {
  const map: Record<string, { tone: "success" | "warning" | "destructive"; label: string }> = {
    paid: { tone: "success", label: "Paid" },
    partial: { tone: "warning", label: "Partial" },
    unpaid: { tone: "destructive", label: "Unpaid" },
  };
  const m = map[status] ?? { tone: "warning" as const, label: status };
  return <Badge tone={m.tone}>{m.label}</Badge>;
}

export function EventStatusBadge({ status }: { status: string }) {
  const map: Record<
    string,
    { tone: "info" | "warning" | "success" | "destructive" | "outline"; label: string }
  > = {
    pending: { tone: "outline", label: "Pending" },
    processing: { tone: "info", label: "Processing" },
    done: { tone: "success", label: "Done" },
    failed: { tone: "warning", label: "Failed" },
    dead: { tone: "destructive", label: "Dead-letter" },
  };
  const m = map[status] ?? { tone: "outline" as const, label: status };
  return <Badge tone={m.tone}>{m.label}</Badge>;
}

export function SourceBadge({ source }: { source: string }) {
  const map: Record<string, { tone: "default" | "primary" | "info"; label: string }> = {
    form: { tone: "default", label: "Form" },
    nlp: { tone: "primary", label: "AI · Text" },
    ocr: { tone: "info", label: "AI · OCR" },
  };
  const m = map[source] ?? { tone: "default" as const, label: source };
  return <Badge tone={m.tone}>{m.label}</Badge>;
}
