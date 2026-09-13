"""Dashboard/report aggregates and the downloadable report endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select

from .. import serializers as ser
from ..analytics import get_revenue_series, load_overview
from ..core.deps import CurrentUser, Db, require
from ..core.roles import P
from ..models import Party, Purchase, Sale
from ..reports import PERIOD_PRESETS, build_report, render_csv, render_pdf

router = APIRouter(prefix="/api", tags=["reports"])

ALLOWED_DAYS = {7, 30, 90, 180, 365}
REPORT_TYPES = {"sales", "purchases", "expenses", "consolidated"}


@router.get("/dashboard", dependencies=[Depends(require(P.DATA_READ))])
def dashboard(ctx: CurrentUser, db: Db) -> dict:
    overview = load_overview(db, ctx.business.id, 14)

    recent_sales = list(
        db.execute(
            select(Sale, Party.name)
            .join(Party, Sale.party_id == Party.id, isouter=True)
            .where(Sale.business_id == ctx.business.id, Sale.status != "cancelled")
            .order_by(Sale.date.desc())
            .limit(5)
        ).all()
    )
    recent_purchases = list(
        db.execute(
            select(Purchase, Party.name)
            .join(Party, Purchase.party_id == Party.id, isouter=True)
            .where(Purchase.business_id == ctx.business.id, Purchase.status != "cancelled")
            .order_by(Purchase.date.desc())
            .limit(5)
        ).all()
    )

    return {
        **overview,
        "recentSales": [ser.sale_row(s, name) for s, name in recent_sales],
        "recentPurchases": [ser.purchase_row(p, name) for p, name in recent_purchases],
        "business": {"name": ctx.business.name, "currency": ctx.business.currency},
    }


@router.get("/reports/overview", dependencies=[Depends(require(P.DATA_READ))])
def reports_overview(ctx: CurrentUser, db: Db) -> dict:
    overview = load_overview(db, ctx.business.id, 14)
    return {**overview, "currency": ctx.business.currency}


@router.get("/reports/revenue", dependencies=[Depends(require(P.DATA_READ))])
def revenue(ctx: CurrentUser, db: Db, days: int = Query(30)) -> dict:
    d = days if days in ALLOWED_DAYS else 30
    series = get_revenue_series(db, ctx.business.id, d)
    return {
        "days": d,
        "points": [{"label": p.label, "value": p.value, "full": p.full} for p in series],
        "currency": ctx.business.currency,
    }


def _build(ctx, db, type_: str, preset: str, date_from: str | None, date_to: str | None):
    if type_ not in REPORT_TYPES:
        raise HTTPException(status_code=400, detail="Unknown report type.")
    if preset not in PERIOD_PRESETS:
        raise HTTPException(status_code=400, detail="Unknown period.")
    return build_report(
        db, ctx.business.id, type_=type_, preset=preset, from_str=date_from, to_str=date_to
    )


@router.get("/reports/preview", dependencies=[Depends(require(P.DATA_READ))])
def preview(
    ctx: CurrentUser,
    db: Db,
    type: str = Query("consolidated"),
    preset: str = Query("month"),
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
) -> dict:
    """The structured report, so the UI can show totals before downloading."""
    report = _build(ctx, db, type, preset, date_from, date_to)
    return {
        "title": report.title,
        "periodLabel": report.periodLabel,
        "rangeLabel": report.rangeLabel,
        "generatedAt": report.generatedAt,
        "summary": report.summary,
        "fileName": report.fileName,
        "empty": report.empty,
        "sections": [
            {
                "key": s.key,
                "title": s.title,
                "columns": s.columns,
                "count": s.count,
                "total": s.total,
                "cancelledCount": s.cancelledCount,
            }
            for s in report.sections
        ],
    }


@router.get("/reports/download", dependencies=[Depends(require(P.DATA_READ))])
def download(
    ctx: CurrentUser,
    db: Db,
    type: str = Query("consolidated"),
    preset: str = Query("month"),
    fmt: str = Query("pdf", pattern="^(pdf|csv)$"),
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
) -> Response:
    report = _build(ctx, db, type, preset, date_from, date_to)
    if report.empty:
        raise HTTPException(status_code=404, detail="No records found for that period.")

    if fmt == "csv":
        body = render_csv(report)
        filename = report.fileName.replace(".pdf", ".csv")
        media = "text/csv; charset=utf-8"
    else:
        body = render_pdf(report)
        filename = report.fileName
        media = "application/pdf"

    return Response(
        content=body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
