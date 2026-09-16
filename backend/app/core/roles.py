"""Roles and the permissions each one carries.

Two of the roles are platform-level and two are tenant-level:

* ``superuser`` and ``admin`` belong to no business. They reach a tenant's data
  by naming it (``?businessId=``), which is what ``CROSS_TENANT`` allows.
* ``owner`` and ``employee`` belong to exactly one business and can never see
  another one.

The split between ``admin`` and ``owner`` is the important one: an admin may
change a business's *configuration* — its profile, tax rate, workflow rules —
but never its *data*. No permission an admin holds can create, amend or delete a
sale, purchase, expense, product or party.

Permissions are coarse on purpose. A finer grid would be more expressive and
much easier to get subtly wrong; these seven map cleanly onto what the endpoints
actually do.
"""

from __future__ import annotations

SUPERUSER = "superuser"
ADMIN = "admin"
OWNER = "owner"
EMPLOYEE = "employee"

#: Every role, most privileged first.
ROLES = (SUPERUSER, ADMIN, OWNER, EMPLOYEE)

#: Roles an owner may hand out from their own team page.
INVITABLE_ROLES = (OWNER, EMPLOYEE)

ROLE_LABELS = {
    SUPERUSER: "Superuser",
    ADMIN: "Admin",
    OWNER: "Business owner",
    EMPLOYEE: "Employee",
}


class P:
    """Permission names. Grouped by the kind of damage they can do."""

    #: Read anything in the business: documents, catalogue, reports, events.
    DATA_READ = "data:read"
    #: Record new business activity — sales, purchases, expenses, payments,
    #: stock adjustments and Smart Input drafts. Additive only. Includes
    #: settling one party's outstanding documents, which is the same act as
    #: taking their payments one by one.
    TXN_WRITE = "txn:write"
    #: Change or undo what is already recorded: cancel, delete, back-date, or
    #: write off every balance in the business at once. Destructive.
    DATA_MANAGE = "data:manage"
    #: Maintain the catalogue: create and edit products and parties.
    CATALOG_WRITE = "catalog:write"
    #: Business configuration: the profile, tax rate, invoice prefix and the
    #: workflow rules. Not data.
    CONFIG_WRITE = "config:write"
    #: Invite, list and remove the people in a business.
    USERS_MANAGE = "users:manage"
    #: Replay and drain the event queue. Re-runs effects, so it is not a read.
    EVENTS_OPERATE = "events:operate"
    #: Act on a business other than your own.
    CROSS_TENANT = "platform:cross-tenant"


_ALL = frozenset(
    {
        P.DATA_READ,
        P.TXN_WRITE,
        P.DATA_MANAGE,
        P.CATALOG_WRITE,
        P.CONFIG_WRITE,
        P.USERS_MANAGE,
        P.EVENTS_OPERATE,
        P.CROSS_TENANT,
    }
)

PERMISSIONS: dict[str, frozenset[str]] = {
    SUPERUSER: _ALL,
    # Reads everything, tunes the business, touches none of its data.
    ADMIN: frozenset({P.DATA_READ, P.CONFIG_WRITE, P.CROSS_TENANT}),
    # Everything inside their own business.
    OWNER: _ALL - {P.CROSS_TENANT},
    # Logs what happened today; cannot undo it.
    EMPLOYEE: frozenset({P.DATA_READ, P.TXN_WRITE}),
}

#: Roles worth locking after repeated failed sign-ins. An employee account is
#: not a useful target, and locking one only gets a shopkeeper's staff stuck at
#: the counter.
THROTTLED_ROLES = frozenset({SUPERUSER, ADMIN, OWNER})

#: Roles that are not attached to a business.
PLATFORM_ROLES = frozenset({SUPERUSER, ADMIN})


def permissions_for(role: str) -> frozenset[str]:
    """Unknown roles get nothing, so a typo in the column cannot open a door."""
    return PERMISSIONS.get(role, frozenset())


def has_permission(role: str, permission: str) -> bool:
    return permission in permissions_for(role)


def is_platform_role(role: str) -> bool:
    return role in PLATFORM_ROLES
