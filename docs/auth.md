# Authentication, roles and permissions

Sessions, the four roles, how RBAC is enforced, and sign-in throttling.

[&larr; Back to the README](../README.md)

---

## Auth

Self-contained email + password, no external provider:

- **PBKDF2-HMAC-SHA256**, 100 000 iterations, stored as `pbkdf2$<salt>$<hash>`
  (`app/core/security.py`). The format is unchanged from the previous implementation,
  so user rows migrated from the old database keep working.
- **Signed JWT session cookie** (PyJWT, HS256), httpOnly, 30 days.
- Unknown ids return 404 rather than leaking existence, and sign-in gives one
  message for both a bad email and a bad password.

`AUTH_SECRET` must be 32+ characters in production.

### Roles and permissions

Four roles, defined in `app/core/roles.py`. Two are platform-level and belong to
no business; two are tenant-level and belong to exactly one.

| Role | Scope | Can |
|---|---|---|
| **Superuser** | every business | everything |
| **Admin** | every business | read anything, change a business's *configuration* — profile, tax rate, invoice prefix, workflow rules. Never its data. |
| **Business owner** | their own business | everything inside it, including the team |
| **Employee** | their own business | record sales, purchases, expenses, payments, stock adjustments and Smart Input drafts; read the catalogue, dashboard and reports |

The admin/owner line is the important one: **no permission an admin holds can
create, amend or delete a sale, purchase, expense, product or party.** An
employee is additive-only — they log what happened, and cannot cancel, delete,
back-date or settle it afterwards.

Permissions are coarse (seven of them) rather than one per endpoint: a finer
grid is more expressive and much easier to get subtly wrong.

```python
# app/core/roles.py
EMPLOYEE: frozenset({P.DATA_READ, P.TXN_WRITE})
ADMIN:    frozenset({P.DATA_READ, P.CONFIG_WRITE, P.CROSS_TENANT})
```

Routes declare what they need, so the handler stays about the handler's job:

```python
@router.delete("/products/{product_id}", dependencies=[Depends(require(P.DATA_MANAGE))])
```

An unrecognised role resolves to *no* permissions, so a typo in the column
closes doors rather than opening them. The SPA hides what a role cannot use
(`lib/session.tsx`), but every rule is enforced again on the API — the UI gating
is only so nobody clicks a button that will 403.

**Cross-tenant access.** A superuser or admin has `business_id = NULL` and names
the business it is acting on with `?businessId=<uuid>`; the SPA keeps that
choice in `lib/api.ts` and appends it to every request. A tenant role is pinned
to its own business, and asking for another one returns 404 rather than 403 — so
the parameter cannot be used to discover other tenants.

**Platform accounts have no sign-up route.** They are created at the console:

```bash
python -m app.cli create-platform-user --role superuser --email you@example.com
python -m app.cli list-platform-users
```

### Team invitations

Sign-up creates a business and its first owner. Everyone else joins by
invitation: an owner creates one on the Team page and gets a `/join/<token>`
link, which the invitee opens to set their own name and password.

Only the SHA-256 of the token is stored, so a leaked database cannot be used to
accept an invitation. The raw token appears once, in the response that creates
it — there is no mail transport here, so the link travels however the business
already reaches its staff. Invitations last seven days, work once, and can be
revoked. A business can never lose its last owner.

### Sign-in throttling

Two independent limits, in `app/core/throttle.py`:

- **Per account** — five failures lock the address for fifteen minutes, and each
  further five doubles it, up to a day. A successful sign-in ends the streak.
- **Per IP** — twenty failures across *all* accounts in fifteen minutes. This is
  what catches password spraying, which never trips the per-account limit.

**Employees are exempt from the account lock**, by design: their accounts are a
poor target and locking one strands a shopkeeper's staff at the counter. They
are still covered by the per-IP limit.

An unknown email is throttled exactly like a real one, so the lockout response
cannot be used to tell which addresses have accounts — with one caveat worth
knowing: it does distinguish an *employee* from everything else, which is the
price of the exemption above.

State lives in Postgres (`login_attempts`) rather than in memory, so two API
processes agree and a restart does not hand an attacker a fresh budget. Moving
it to Redis later means reimplementing one function. The thresholds are settings
(`LOGIN_MAX_ATTEMPTS`, `LOGIN_LOCK_MINUTES`, `LOGIN_WINDOW_MINUTES`,
`LOGIN_MAX_IP_ATTEMPTS`).

---

