import { useState } from "react";
import { api, useApi, useMutation } from "@/lib/api";
import { PageHeader, PageState, EmptyState, SectionCard } from "@/components/ui/misc";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Field, Input, Select } from "@/components/ui/input";
import { Icon } from "@/components/Icon";
import { ConfirmButton } from "@/components/ConfirmButton";
import { useSession } from "@/lib/session";
import { formatDate } from "@/lib/utils";

interface Member {
  id: string;
  name: string;
  email: string;
  role: string;
  roleLabel: string;
  createdAt: string;
}

interface PendingInvite {
  id: string;
  email: string;
  role: string;
  roleLabel: string;
  expiresAt: string;
  createdAt: string;
}

interface TeamData {
  members: Member[];
  invites: PendingInvite[];
  roles: { value: string; label: string }[];
}

export function Team() {
  const { data, loading, error, reload } = useApi<TeamData>("/users");
  const { me } = useSession();
  const [open, setOpen] = useState(false);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Team"
        description="Who can sign in to this business, and what they are allowed to do."
      >
        <Button onClick={() => setOpen(true)}>
          <Icon name="plus" size={16} />
          Invite someone
        </Button>
      </PageHeader>

      <PageState loading={loading} error={error} />

      {data && (
        <>
          <SectionCard title="Members" description={`${data.members.length} with an account`}>
            <Table>
              <THead>
                <TR>
                  <TH>Name</TH>
                  <TH>Email</TH>
                  <TH>Role</TH>
                  <TH>Joined</TH>
                  <TH className="text-right">Actions</TH>
                </TR>
              </THead>
              <TBody>
                {data.members.map((m) => (
                  <TR key={m.id}>
                    <TD className="font-medium">
                      {m.name}
                      {m.id === me.user.id && (
                        <span className="ml-2 text-xs text-muted-foreground">you</span>
                      )}
                    </TD>
                    <TD className="text-muted-foreground">{m.email}</TD>
                    <TD>
                      <Badge tone={m.role === "owner" ? "primary" : "default"}>{m.roleLabel}</Badge>
                    </TD>
                    <TD className="text-muted-foreground">{formatDate(m.createdAt)}</TD>
                    <TD className="text-right">
                      {m.id !== me.user.id && (
                        <div className="flex items-center justify-end gap-2">
                          <RoleSwitch member={m} roles={data.roles} onDone={reload} />
                          <ConfirmButton
                            danger
                            title="Remove from the team"
                            message={`${m.name} will lose access to this business immediately. Their recorded sales and purchases stay.`}
                            confirmLabel="Remove"
                            action={() => api.del(`/users/${m.id}`)}
                            onDone={reload}
                          >
                            <Icon name="trash" size={16} />
                          </ConfirmButton>
                        </div>
                      )}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </SectionCard>

          <SectionCard
            title="Pending invitations"
            description="Links that have been handed out but not used yet."
          >
            {data.invites.length === 0 ? (
              <EmptyState
                title="No pending invitations"
                description="Invite someone and share the link with them."
              />
            ) : (
              <Table>
                <THead>
                  <TR>
                    <TH>Email</TH>
                    <TH>Role</TH>
                    <TH>Expires</TH>
                    <TH className="text-right">Actions</TH>
                  </TR>
                </THead>
                <TBody>
                  {data.invites.map((i) => (
                    <TR key={i.id}>
                      <TD className="font-medium">{i.email}</TD>
                      <TD>
                        <Badge>{i.roleLabel}</Badge>
                      </TD>
                      <TD className="text-muted-foreground">{formatDate(i.expiresAt)}</TD>
                      <TD className="text-right">
                        <ConfirmButton
                          danger
                          title="Revoke invitation"
                          message={`The link sent to ${i.email} will stop working.`}
                          confirmLabel="Revoke"
                          action={() => api.del(`/users/invites/${i.id}`)}
                          onDone={reload}
                        >
                          <Icon name="trash" size={16} />
                        </ConfirmButton>
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            )}
          </SectionCard>
        </>
      )}

      <InviteModal
        open={open}
        roles={data?.roles ?? []}
        onClose={() => setOpen(false)}
        onDone={reload}
      />
    </div>
  );
}

function RoleSwitch({
  member,
  roles,
  onDone,
}: {
  member: Member;
  roles: { value: string; label: string }[];
  onDone: () => void;
}) {
  const { run, pending } = useMutation();
  return (
    <Select
      className="h-8 w-36 text-xs"
      value={member.role}
      disabled={pending}
      onChange={(e) =>
        run(
          () => api.put(`/users/${member.id}/role`, { email: member.email, role: e.target.value }),
          onDone,
        )
      }
    >
      {roles.map((r) => (
        <option key={r.value} value={r.value}>
          {r.label}
        </option>
      ))}
    </Select>
  );
}

function InviteModal({
  open,
  roles,
  onClose,
  onDone,
}: {
  open: boolean;
  roles: { value: string; label: string }[];
  onClose: () => void;
  onDone: () => void;
}) {
  const { run, pending, error } = useMutation();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("employee");
  const [link, setLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  function close() {
    setLink(null);
    setEmail("");
    setCopied(false);
    onClose();
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    await run(
      () => api.post<{ joinUrl: string }>("/users/invites", { email, role }),
      (created) => {
        setLink(created.joinUrl);
        onDone();
      },
    );
  }

  return (
    <Modal
      open={open}
      onClose={close}
      title="Invite someone"
      description="They pick their own password when they follow the link."
    >
      <div className="p-5">
        {link ? (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-muted-foreground">
              Send this link to <span className="font-medium text-foreground">{email}</span>. It
              works once and expires in seven days.
            </p>
            {/* Shown here and nowhere else — the server only keeps its hash. */}
            <div className="flex items-center gap-2">
              <Input readOnly value={link} onFocus={(e) => e.currentTarget.select()} />
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  navigator.clipboard?.writeText(link).then(
                    () => setCopied(true),
                    () => setCopied(false),
                  );
                }}
              >
                {copied ? "Copied" : "Copy"}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              This link is not shown again. If you lose it, revoke the invitation and make a new
              one.
            </p>
            <div className="mt-2 flex justify-end">
              <Button onClick={close}>Done</Button>
            </div>
          </div>
        ) : (
          <form onSubmit={submit} className="flex flex-col gap-4">
            <Field label="Email">
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="them@business.com"
                required
              />
            </Field>
            <Field
              label="Role"
              hint="Employees can record sales, purchases and expenses, but cannot delete anything or change settings."
            >
              <Select value={role} onChange={(e) => setRole(e.target.value)}>
                {roles.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </Select>
            </Field>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <div className="mt-1 flex justify-end gap-2">
              <Button type="button" variant="secondary" onClick={close}>
                Cancel
              </Button>
              <Button type="submit" disabled={pending}>
                {pending ? "Creating…" : "Create invitation"}
              </Button>
            </div>
          </form>
        )}
      </div>
    </Modal>
  );
}
