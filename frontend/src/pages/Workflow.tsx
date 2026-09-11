import { useState } from "react";
import { api, useApi, useMutation } from "@/lib/api";
import { PageHeader, PageState, EmptyState, SectionCard } from "@/components/ui/misc";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Modal } from "@/components/ui/modal";
import { Field, Input, Select } from "@/components/ui/input";
import { Icon } from "@/components/Icon";
import { ConfirmButton } from "@/components/ConfirmButton";
import { cn, formatDateTime } from "@/lib/utils";

interface Rule {
  id: string;
  name: string;
  eventType: string;
  conditionField: string | null;
  conditionOp: string | null;
  conditionValue: string | null;
  actionType: string;
  actionConfig: Record<string, unknown>;
  enabled: boolean;
  builtIn: boolean;
}

interface Execution {
  id: string;
  ruleName: string;
  eventType: string;
  status: string;
  detail: string | null;
  createdAt: string;
}

interface WorkflowData {
  rules: Rule[];
  executions: Execution[];
  eventTypes: { value: string; label: string }[];
}

const ACTIONS = [
  { value: "notify", label: "Create a notification" },
  { value: "restock_alert", label: "Low-stock alert" },
  { value: "flag_expense", label: "Flag the expense" },
  { value: "update_inventory", label: "Update inventory" },
];

const OPS = [
  { value: "", label: "Always" },
  { value: "gt", label: "greater than" },
  { value: "gte", label: "at least" },
  { value: "lt", label: "less than" },
  { value: "lte", label: "at most" },
  { value: "eq", label: "equals" },
  { value: "neq", label: "not equal to" },
];

const STATUS_TONE: Record<string, "success" | "outline" | "destructive"> = {
  matched: "success",
  skipped: "outline",
  error: "destructive",
};

export function Workflow() {
  const { data, loading, error, reload } = useApi<WorkflowData>("/workflow");
  const { run, pending } = useMutation();
  const [editing, setEditing] = useState<Rule | null>(null);
  const [creating, setCreating] = useState(false);

  if (!data) return <PageState loading={loading} error={error} />;
  const labels = new Map(data.eventTypes.map((t) => [t.value, t.label]));

  return (
    <div className="space-y-6">
      <PageHeader
        title="Workflow"
        description="WHEN an event happens, THEN do something. Rules run inside the event transaction."
      >
        <Button onClick={() => setCreating(true)}>
          <Icon name="plus" size={16} /> New rule
        </Button>
      </PageHeader>

      <SectionCard
        title="Rules"
        description="Toggle a rule off to stop it firing, without deleting it"
      >
        {data.rules.length === 0 ? (
          <div className="p-6">
            <EmptyState icon={<Icon name="workflow" />} title="No rules yet" />
          </div>
        ) : (
          <Table>
            <THead>
              <TR className="hover:bg-transparent">
                <TH>Rule</TH>
                <TH>When</TH>
                <TH>Condition</TH>
                <TH>Then</TH>
                <TH className="text-right">Actions</TH>
              </TR>
            </THead>
            <TBody>
              {data.rules.map((r) => (
                <TR key={r.id}>
                  <TD>
                    <div className="flex items-center gap-2">
                      <span
                        className={cn(
                          "font-medium",
                          !r.enabled && "text-muted-foreground line-through",
                        )}
                      >
                        {r.name}
                      </span>
                      {r.builtIn && <Badge tone="default">Built-in</Badge>}
                    </div>
                  </TD>
                  <TD className="text-muted-foreground">
                    {labels.get(r.eventType) ?? r.eventType}
                  </TD>
                  <TD className="text-muted-foreground">
                    {r.conditionField
                      ? `${r.conditionField} ${OPS.find((o) => o.value === r.conditionOp)?.label ?? r.conditionOp} ${r.conditionValue}`
                      : "Always"}
                  </TD>
                  <TD className="text-muted-foreground">
                    {ACTIONS.find((a) => a.value === r.actionType)?.label ?? r.actionType}
                  </TD>
                  <TD>
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={pending}
                        onClick={() =>
                          run(() => api.post(`/workflow/rules/${r.id}/toggle`), reload)
                        }
                      >
                        {r.enabled ? "Disable" : "Enable"}
                      </Button>
                      <button
                        onClick={() => setEditing(r)}
                        aria-label="Edit rule"
                        className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
                      >
                        <Icon name="edit" size={16} />
                      </button>
                      {!r.builtIn && (
                        <ConfirmButton
                          action={() => api.del(`/workflow/rules/${r.id}`)}
                          title="Delete rule?"
                          message={`"${r.name}" will stop running and be removed.`}
                          confirmLabel="Delete"
                          danger
                          onDone={reload}
                          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-destructive"
                        >
                          <Icon name="trash" size={16} />
                        </ConfirmButton>
                      )}
                    </div>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </SectionCard>

      <SectionCard title="Recent rule runs" description="An audit trail of every evaluation">
        {data.executions.length === 0 ? (
          <div className="p-6">
            <EmptyState icon={<Icon name="events" />} title="Nothing has run yet" />
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {data.executions.map((x) => (
              <li key={x.id} className="flex items-center gap-3 px-5 py-3 text-sm">
                <Badge tone={STATUS_TONE[x.status] ?? "outline"}>{x.status}</Badge>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{x.ruleName}</div>
                  <div className="text-xs text-muted-foreground">{x.detail ?? "-"}</div>
                </div>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {formatDateTime(x.createdAt)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      <RuleDialog
        open={creating || editing !== null}
        rule={editing}
        eventTypes={data.eventTypes}
        onClose={() => {
          setCreating(false);
          setEditing(null);
        }}
        onSaved={() => {
          setCreating(false);
          setEditing(null);
          reload();
        }}
      />
    </div>
  );
}

function RuleDialog({
  open,
  rule,
  eventTypes,
  onClose,
  onSaved,
}: {
  open: boolean;
  rule: Rule | null;
  eventTypes: { value: string; label: string }[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const { run, pending, error } = useMutation();
  const [seeded, setSeeded] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: "",
    eventType: "SALE_CREATED",
    conditionField: "",
    conditionOp: "",
    conditionValue: "",
    actionType: "notify",
    title: "",
  });

  const key = rule?.id ?? (open ? "new" : null);
  if (open && key !== seeded) {
    setSeeded(key);
    setForm({
      name: rule?.name ?? "",
      eventType: rule?.eventType ?? "SALE_CREATED",
      conditionField: rule?.conditionField ?? "",
      conditionOp: rule?.conditionOp ?? "",
      conditionValue: rule?.conditionValue ?? "",
      actionType: rule?.actionType ?? "notify",
      title: (rule?.actionConfig?.title as string) ?? "",
    });
  }
  if (!open && seeded !== null) setSeeded(null);

  const set =
    (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const body = {
      name: form.name,
      eventType: form.eventType,
      conditionField: form.conditionOp ? form.conditionField || null : null,
      conditionOp: form.conditionOp || null,
      conditionValue: form.conditionOp ? form.conditionValue || null : null,
      actionType: form.actionType,
      actionConfig: form.title ? { title: form.title } : {},
      enabled: rule?.enabled ?? true,
    };
    await run(
      () =>
        rule ? api.put(`/workflow/rules/${rule.id}`, body) : api.post("/workflow/rules", body),
      onSaved,
    );
  }

  return (
    <Modal open={open} onClose={onClose} title={rule ? "Edit rule" : "New rule"}>
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Field label="Rule name">
          <Input
            value={form.name}
            onChange={set("name")}
            placeholder="Alert on large sales"
            required
          />
        </Field>
        <Field label="WHEN this event happens">
          <Select value={form.eventType} onChange={set("eventType")}>
            {eventTypes.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </Select>
        </Field>

        <div className="grid grid-cols-3 gap-3">
          <Field label="Field">
            <Input
              value={form.conditionField}
              onChange={set("conditionField")}
              placeholder="amount"
            />
          </Field>
          <Field label="Operator">
            <Select value={form.conditionOp} onChange={set("conditionOp")}>
              {OPS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Value">
            <Input
              value={form.conditionValue}
              onChange={set("conditionValue")}
              placeholder="10000"
            />
          </Field>
        </div>

        <Field label="THEN do this">
          <Select value={form.actionType} onChange={set("actionType")}>
            {ACTIONS.map((a) => (
              <option key={a.value} value={a.value}>
                {a.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Alert title" hint="Shown on the notification this rule creates.">
          <Input value={form.title} onChange={set("title")} placeholder="Large sale recorded" />
        </Field>

        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button type="submit" disabled={pending}>
            {pending ? "Saving…" : rule ? "Save changes" : "Create rule"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
