"""Downloadable business reports (structured data, PDF and CSV).

Cancelled documents are listed but excluded from totals (the accountant-correct
behaviour). Amounts are printed as plain grouped numbers with the currency
stated once in the header, because the PDF core fonts have no rupee glyph.
"""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from .core.utils import end_of_day, group_number, parse_date_input, round2, start_of_day
from .models import Business, Expense, Party, Purchase, Sale

ReportType = str  # sales | purchases | expenses | consolidated
PeriodPreset = str

PERIOD_PRESETS = (
    "today",
    "week",
    "month",
    "last_month",
    "quarter",
    "half_year",
    "year",
    "last_12_months",
    "custom",
)

TITLES = {
    "sales": "Sales Report",
    "purchases": "Purchases Report",
    "expenses": "Expenses Report",
    "consolidated": "Consolidated Business Report",
}


@dataclass(slots=True)
class ReportSection:
    key: str
    title: str
    columns: list[str]
    #: Column indexes holding numbers (right-aligned in the PDF).
    numericColumns: list[int]
    rows: list[list[str]]
    count: int
    #: Net total, excluding cancelled documents.
    total: float
    cancelledCount: int


@dataclass(slots=True)
class BusinessReport:
    business: dict
    title: str
    periodLabel: str
    rangeLabel: str
    generatedAt: str
    sections: list[ReportSection] = field(default_factory=list)
    summary: list[dict] = field(default_factory=list)
    fileName: str = "report.pdf"
    empty: bool = True


def _num(n: float) -> str:
    return group_number(n or 0)


def _short_date(d: datetime) -> str:
    return d.strftime("%d %b %Y")


def resolve_period(
    preset: PeriodPreset, from_str: str | None = None, to_str: str | None = None
) -> tuple[datetime, datetime, str]:
    now = datetime.now()
    y, m = now.year, now.month

    if preset == "today":
        return start_of_day(now), end_of_day(now), "Today"
    if preset == "week":
        return start_of_day(now) - timedelta(days=6), end_of_day(now), "Last 7 days"
    if preset == "month":
        return datetime(y, m, 1), end_of_day(now), "This month"
    if preset == "last_month":
        first_this = datetime(y, m, 1)
        last_month_end = first_this - timedelta(days=1)
        return (
            datetime(last_month_end.year, last_month_end.month, 1),
            end_of_day(last_month_end),
            "Last month",
        )
    if preset == "quarter":
        return start_of_day(now) - timedelta(days=90), end_of_day(now), "Last 3 months"
    if preset == "half_year":
        return start_of_day(now) - timedelta(days=182), end_of_day(now), "Last 6 months"
    if preset == "year":
        return datetime(y, 1, 1), end_of_day(now), f"This year ({y})"
    if preset == "last_12_months":
        return start_of_day(now) - timedelta(days=365), end_of_day(now), "Last 12 months"

    # custom
    f = parse_date_input(from_str)
    t = parse_date_input(to_str)
    start = start_of_day(f) if f else datetime(y, m, 1)
    end = end_of_day(t) if t else end_of_day(now)
    # A backwards range would silently return nothing, so swap it instead.
    if start > end:
        start, end = start_of_day(end), end_of_day(start)
    return start, end, "Custom range"


def build_report(
    db: Session,
    business_id: uuid.UUID,
    *,
    type_: ReportType,
    preset: PeriodPreset,
    from_str: str | None = None,
    to_str: str | None = None,
) -> BusinessReport:
    start, end, label = resolve_period(preset, from_str, to_str)
    biz = db.scalar(select(Business).where(Business.id == business_id))
    if biz is None:
        raise ValueError("Business not found.")
    cur = biz.currency

    want_sales = type_ in ("sales", "consolidated")
    want_purchases = type_ in ("purchases", "consolidated")
    want_expenses = type_ in ("expenses", "consolidated")

    sections: list[ReportSection] = []
    sales_total = purchases_total = expenses_total = 0.0

    if want_sales:
        rows = list(
            db.execute(
                select(Sale, Party.name)
                .join(Party, Sale.party_id == Party.id, isouter=True)
                .where(Sale.business_id == business_id, Sale.date >= start, Sale.date <= end)
                .order_by(Sale.date.asc())
            ).all()
        )
        cancelled = 0
        body: list[list[str]] = []
        for sale, party_name in rows:
            if sale.status == "cancelled":
                cancelled += 1
            else:
                sales_total += sale.total
            due = 0 if sale.status == "cancelled" else round2(sale.total - sale.amount_paid)
            body.append(
                [
                    _short_date(sale.date),
                    sale.invoice_number,
                    party_name or "Walk-in",
                    _num(sale.subtotal),
                    _num(sale.discount_amount),
                    _num(sale.tax),
                    _num(sale.total),
                    _num(sale.amount_paid),
                    _num(due),
                    "Cancelled" if sale.status == "cancelled" else sale.payment_status,
                ]
            )
        sales_total = round2(sales_total)
        sections.append(
            ReportSection(
                key="sales",
                title="Sales",
                columns=[
                    "Date",
                    "Invoice",
                    "Customer",
                    "Subtotal",
                    "Discount",
                    "Tax",
                    "Total",
                    "Paid",
                    "Due",
                    "Status",
                ],
                numericColumns=[3, 4, 5, 6, 7, 8],
                rows=body,
                count=len(rows),
                total=sales_total,
                cancelledCount=cancelled,
            )
        )

    if want_purchases:
        rows = list(
            db.execute(
                select(Purchase, Party.name)
                .join(Party, Purchase.party_id == Party.id, isouter=True)
                .where(
                    Purchase.business_id == business_id,
                    Purchase.date >= start,
                    Purchase.date <= end,
                )
                .order_by(Purchase.date.asc())
            ).all()
        )
        cancelled = 0
        body = []
        for pur, party_name in rows:
            if pur.status == "cancelled":
                cancelled += 1
            else:
                purchases_total += pur.total
            due = 0 if pur.status == "cancelled" else round2(pur.total - pur.amount_paid)
            body.append(
                [
                    _short_date(pur.date),
                    pur.reference_number,
                    party_name or "-",
                    _num(pur.subtotal),
                    _num(pur.discount_amount),
                    _num(pur.tax),
                    _num(pur.total),
                    _num(pur.amount_paid),
                    _num(due),
                    "Cancelled" if pur.status == "cancelled" else pur.payment_status,
                ]
            )
        purchases_total = round2(purchases_total)
        sections.append(
            ReportSection(
                key="purchases",
                title="Purchases",
                columns=[
                    "Date",
                    "Reference",
                    "Supplier",
                    "Subtotal",
                    "Discount",
                    "Tax",
                    "Total",
                    "Paid",
                    "Due",
                    "Status",
                ],
                numericColumns=[3, 4, 5, 6, 7, 8],
                rows=body,
                count=len(rows),
                total=purchases_total,
                cancelledCount=cancelled,
            )
        )

    if want_expenses:
        rows = list(
            db.scalars(
                select(Expense)
                .where(
                    Expense.business_id == business_id, Expense.date >= start, Expense.date <= end
                )
                .order_by(Expense.date.asc())
            )
        )
        expenses_total = round2(sum(e.amount for e in rows))
        sections.append(
            ReportSection(
                key="expenses",
                title="Expenses",
                columns=["Date", "Category", "Description", "Amount"],
                numericColumns=[3],
                rows=[
                    [_short_date(e.date), e.category, e.description, _num(e.amount)] for e in rows
                ],
                count=len(rows),
                total=expenses_total,
                cancelledCount=0,
            )
        )

    summary: list[dict] = []
    if want_sales:
        summary.append({"label": "Total sales", "value": f"{cur} {_num(sales_total)}"})
    if want_purchases:
        summary.append({"label": "Total purchases", "value": f"{cur} {_num(purchases_total)}"})
    if want_expenses:
        summary.append({"label": "Total expenses", "value": f"{cur} {_num(expenses_total)}"})
    if type_ == "consolidated":
        summary.append(
            {
                "label": "Net cash (sales - purchases - expenses)",
                "value": f"{cur} {_num(round2(sales_total - purchases_total - expenses_total))}",
                "strong": True,
            }
        )
    for sec in sections:
        summary.append(
            {
                "label": f"{sec.title} recorded",
                "value": f"{sec.count} ({sec.cancelledCount} cancelled)"
                if sec.cancelledCount
                else str(sec.count),
            }
        )

    stamp = f"{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}"
    slug = "".join(c if c.isalnum() else "-" for c in biz.name.lower()).strip("-") or "business"
    while "--" in slug:
        slug = slug.replace("--", "-")

    return BusinessReport(
        business={
            "name": biz.name,
            "address": biz.address,
            "gstNumber": biz.gst_number,
            "currency": cur,
        },
        title=TITLES.get(type_, "Business Report"),
        periodLabel=label,
        rangeLabel=f"{_short_date(start)} to {_short_date(end)}",
        generatedAt=datetime.now().strftime("%d %b %Y, %H:%M"),
        sections=sections,
        summary=summary,
        fileName=f"{slug}-{type_}-{stamp}.pdf",
        empty=all(not s.rows for s in sections),
    )


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------
def render_csv(report: BusinessReport) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([report.business["name"], report.title])
    w.writerow([report.periodLabel, report.rangeLabel])
    w.writerow([f"Amounts in {report.business['currency']}"])
    w.writerow([])
    for s in report.summary:
        w.writerow([s["label"], s["value"]])
    for section in report.sections:
        w.writerow([])
        w.writerow([section.title])
        w.writerow(section.columns)
        for row in section.rows:
            w.writerow(row)
    return buf.getvalue().encode("utf-8-sig")


def _page_footer(canvas, doc, report: BusinessReport) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#8a8a8a"))
    width, _ = landscape(A4)
    canvas.drawString(15 * mm, 10 * mm, f"{report.business['name']} · {report.title}")
    canvas.drawRightString(width - 15 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def render_pdf(report: BusinessReport) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title=report.title,
        author=report.business["name"],
    )

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1x", parent=styles["Heading1"], fontSize=15, spaceAfter=2, leading=18)
    meta = ParagraphStyle(
        "metax",
        parent=styles["Normal"],
        fontSize=8.5,
        textColor=colors.HexColor("#666666"),
        leading=12,
    )
    meta_r = ParagraphStyle("metar", parent=meta, alignment=TA_RIGHT)
    h2 = ParagraphStyle("h2x", parent=styles["Heading2"], fontSize=11, spaceBefore=8, spaceAfter=4)

    story: list = []

    # Header: business on the left, report meta on the right.
    left = [Paragraph(report.business["name"], h1)]
    if report.business.get("address"):
        left.append(Paragraph(report.business["address"], meta))
    if report.business.get("gstNumber"):
        left.append(Paragraph(f"GSTIN: {report.business['gstNumber']}", meta))
    right = [
        Paragraph(f"<b>{report.title}</b>", meta_r),
        Paragraph(f"{report.periodLabel}: {report.rangeLabel}", meta_r),
        Paragraph(f"Generated {report.generatedAt}", meta_r),
        Paragraph(f"Amounts in {report.business['currency']}", meta_r),
    ]
    header = Table([[left, right]], colWidths=[doc.width * 0.55, doc.width * 0.45])
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("LINEBELOW", (0, 0), (-1, -1), 0.6, colors.HexColor("#d0d0d0")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story += [header, Spacer(1, 10)]

    # Summary
    story.append(Paragraph("Summary", h2))
    summary_rows = [[s["label"], s["value"]] for s in report.summary]
    if summary_rows:
        t = Table(summary_rows, colWidths=[doc.width * 0.32, doc.width * 0.20], hAlign="LEFT")
        t.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#555555")),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(t)
    story.append(Spacer(1, 12))

    # Sections
    for section in report.sections:
        story.append(Paragraph(f"{section.title} ({section.count})", h2))
        if not section.rows:
            story += [Paragraph("No records in this period.", meta), Spacer(1, 8)]
            continue

        data = [section.columns, *section.rows]
        table = Table(data, repeatRows=1, hAlign="LEFT")
        style = [
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f7")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#222222")),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e2e8")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fbfbfd")]),
        ]
        for col in section.numericColumns:
            style.append(("ALIGN", (col, 1), (col, -1), "RIGHT"))
        table.setStyle(TableStyle(style))
        story += [table, Spacer(1, 14)]

    doc.build(
        story,
        onFirstPage=lambda c, d: _page_footer(c, d, report),
        onLaterPages=lambda c, d: _page_footer(c, d, report),
    )
    return buf.getvalue()
