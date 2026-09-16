# Feature reference

What each page does: sales, purchases, stock, parties, reports and alerts.

[&larr; Back to the README](../README.md)

---

## Feature tour

### Dashboard
Six KPI cards (sales, purchases, expenses, inventory value, receivable, payable),
each clicking through to its page. Revenue chart, a heuristic **business-health
score** (inventory / revenue / expenses / cash flow), Recent Sales and Recent
Purchases side by side, and a low-stock "Needs attention" panel.

### Smart Input (`/input`)
Two modes: **natural language** (type `Sold 10 rice bags to Kumar Traders`) and
**image / OCR** (upload an invoice, order slip or WhatsApp screenshot). Either way
you land on a **confirmation screen** with the extracted party, line items,
discount and date, all editable, before anything is written. Typed text and the
parsed draft both survive navigating away and back, until the draft is published.

### Sales & Purchases
Full list with source badge (Form / AI·Text / AI·OCR) and payment status. Click
**any row** for a detail modal with line items, totals, and a click-to-edit
transaction date. Inline "Record payment" and "Cancel"; cancelling reverses
inventory and the party balance. Sales also have a printable invoice at
`/sales/:id`.

Both support **discounts** (flat amount or percentage) applied to the subtotal
before tax, with a live preview while you type and a hard block when the discount
exceeds the document value.

### Transaction dates
Every sale and purchase carries a business `date` separate from `created_at`. It
defaults to today, can be set at creation, and corrected afterwards from the
detail modal, for entries logged late. Lists, charts, analytics and reports all
key off this date.

### Parties (`/parties`)
Customers and suppliers with running balances. Each party row expands to show the
individual unpaid invoices/bills behind its balance, with **"Pay all"** per party
and **"Mark all as paid"** for all receivables or all payables. Phone numbers use
a country-code dropdown (202 countries).

"Pay all" for one party needs the same permission as taking a payment against a
single bill, so an employee can use it; "Mark all as paid" across the business
is owner-only.

### Products, Expenses, Notifications
Inventory with stock, HSN/SKU, low-stock thresholds and a stock-movement history;
manual stock adjustments that can never drive stock negative; categorised expenses
with their own dates; an alerts inbox fed by the workflow engine.

### Alert log

Alerts are raised by workflow rules and listed on the Notifications page. Each
one records **which rule fired, on which event, and therefore who caused it**
(`notifications.event_id` / `rule_id`, migration `0005`) — the difference
between a message and something you can audit.

The list filters by severity and by unread, and an alert can be marked unread
again, dismissed, or cleared in bulk once dealt with. Reading and marking need
`data:read`; **dismissing and "Clear read" need `data:manage`**, so those two
buttons are hidden from employees and admins rather than offered and refused. Both source columns are
nullable and `SET NULL` on delete: an alert outlives the rule that raised it
rather than vanishing with it, and shows no source instead.

The notify action dedupes against *unread* alerts of the same title, so a noisy
rule cannot bury the one that matters.

---

## Reports (`/reports`)
KPI cards, a **revenue chart** with a Y axis, hover tooltips showing exact values,
and a range selector (last week / month / 3 / 6 months / year) that buckets daily,
weekly or monthly as appropriate. Top products, top customers, expenses by
category, cash-flow summary, and **downloadable reports** (see below).

### Workflow (`/workflow`) and Event bus (`/events`)
Toggle built-in rules or add your own `WHEN <event> [condition] THEN <action>`
rule. The event bus page shows events flowing `pending → done`, with retry,
dead-letter, replay and a manual drain, and polls while open.

---

## Reports

`app/reports.py` builds a report for a **type** (sales, purchases, expenses, or
everything consolidated) over a **period**: today, last 7 days, this month, last
month, last 3 / 6 months, this year, last 12 months, or a custom range. It renders
server-side to **PDF** (reportlab, landscape A4, repeating table headers and page
numbers) or **CSV**, served as a normal download:

```
GET /api/reports/download?type=consolidated&preset=month&fmt=pdf
GET /api/reports/preview?type=sales&preset=last_12_months     # totals as JSON
```

Two deliberate details: cancelled documents are **listed but excluded from
totals** (the accountant-correct behaviour), and amounts print as plain grouped
numbers with the currency stated once in the header, because the PDF core fonts
have no rupee glyph.

Invoices print in **light mode regardless of the app theme**: the print handler
temporarily removes the `.dark` class and the app chrome is hidden with
`print:hidden`, so only the invoice reaches the page.

---

