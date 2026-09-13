"""Cross-tenant routes for the platform roles.

A superuser or admin has no business of its own, so it needs a way to see which
businesses exist before it can name one with `?businessId=`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from ..core.deps import Db, SessionUser, require_global
from ..core.roles import P
from ..models import Business, Sale, User

router = APIRouter(
    prefix="/api/businesses",
    tags=["platform"],
    dependencies=[Depends(require_global(P.CROSS_TENANT))],
)


@router.get("")
def list_businesses(ctx: SessionUser, db: Db) -> dict:
    """Every tenant, with enough context to pick one."""
    members = dict(
        db.execute(select(User.business_id, func.count(User.id)).group_by(User.business_id)).all()
    )
    sales = dict(
        db.execute(select(Sale.business_id, func.count(Sale.id)).group_by(Sale.business_id)).all()
    )
    rows = list(db.scalars(select(Business).order_by(Business.name)))
    return {
        "rows": [
            {
                "id": str(b.id),
                "name": b.name,
                "currency": b.currency,
                "taxRate": b.tax_rate,
                "members": members.get(b.id, 0),
                "sales": sales.get(b.id, 0),
                "createdAt": b.created_at.isoformat(),
            }
            for b in rows
        ]
    }
