"use client";

import { useState, useTransition } from "react";
import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/input";
import { Icon } from "@/components/icons";
import { buildReportAction } from "./actions";
import type { BusinessReport, PeriodPreset, ReportType } from "@/lib/reports";

const TYPES: { value: ReportType; label: string }[] = [
  { value: "consolidated", label: "Everything (consolidated)" },
  { value: "sales", label: "Sales" },
  { value: "purchases", label: "Purchases" },
  { value: "expenses", label: "Expenses" },
];

const PERIODS: { value: PeriodPreset; label: string }[] = [
  { value: "today", label: "Today" },
  { value: "week", label: "Last 7 days" },
  { value: "month", label: "This month" },
  { value: "last_month", label: "Last month" },
  { value: "quarter", label: "Last 3 months" },
  { value: "half_year", label: "Last 6 months" },
  { value: "year", label: "This year" },
  { value: "last_12_months", label: "Last 12 months" },
  { value: "custom", label: "Custom range" },
];

/** Escapes a CSV cell (quotes, commas and newlines). */
function csvCell(v: string): string {
  return /[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
}

function downloadBlob(content: string, fileName: string, mime: string) {
  const url = URL.createObjectURL(new Blob([content], { type: mime }));
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function renderPdf(report: BusinessReport) {
  // Loaded on demand so jsPDF stays out of the initial page bundle.
  const [{ jsPDF }, { default: autoTable }] = await Promise.all([
    import("jspdf"),
    import("jspdf-autotable"),
  ]);

  const doc = new jsPDF({ orientation: "landscape", unit: "pt", format: "a4" });
  const pageW = doc.internal.pageSize.getWidth();
  const margin = 32;
  let y = margin;

  // ---- Header -------------------------------------------------------------
  doc.setFont("helvetica", "bold").setFontSize(16).setTextColor(20);
  doc.text(report.business.name, margin, y);

  doc.setFont("helvetica", "bold").setFontSize(12);
  doc.text(report.title, pageW - margin, y, { align: "right" });
  y += 16;

  doc.setFont("helvetica", "normal").setFontSize(9).setTextColor(110);
  const leftLines = [report.business.address ?? "", report.business.gstNumber ? `GSTIN: ${report.business.gstNumber}` : ""].filter(Boolean);
  const rightLines = [
    `${report.periodLabel}: ${report.rangeLabel}`,
    `Generated ${report.generatedAt}`,
    `Amounts in ${report.business.currency}`,
  ];
  const rows = Math.max(leftLines.length, rightLines.length);
  for (let i = 0; i < rows; i++) {
    if (leftLines[i]) doc.text(leftLines[i], margin, y);
    if (rightLines[i]) doc.text(rightLines[i], pageW - margin, y, { align: "right" });
    y += 12;
  }

  y += 4;
  doc.setDrawColor(210).line(margin, y, pageW - margin, y);
  y += 16;

  // ---- Summary ------------------------------------------------------------
  autoTable(doc, {
    startY: y,
    head: [["Summary", ""]],
    body: report.summary.map((s) => [s.label, s.value]),
    theme: "plain",
    styles: { fontSize: 9, cellPadding: 4 },
    headStyles: { fontStyle: "bold", fontSize: 10, textColor: 20 },
    columnStyles: { 0: { cellWidth: 260 }, 1: { halign: "right", fontStyle: "bold" } },
    margin: { left: margin, right: margin },
    tableWidth: 420,
  });
  y = (doc as unknown as { lastAutoTable?: { finalY?: number } }).lastAutoTable?.finalY ?? y;
  y += 22;

  // ---- Sections -----------------------------------------------------------
  for (const section of report.sections) {
    doc.setFont("helvetica", "bold").setFontSize(11).setTextColor(20);
    doc.text(`${section.title} (${section.count})`, margin, y);
    y += 8;

    if (section.rows.length === 0) {
      y += 8;
      doc.setFont("helvetica", "normal").setFontSize(9).setTextColor(130);
      doc.text("No records in this period.", margin, y);
      y += 24;
      continue;
    }

    const columnStyles: Record<number, { halign: "right" }> = {};
    for (const i of section.numericColumns) columnStyles[i] = { halign: "right" };

    autoTable(doc, {
      startY: y,
      head: [section.columns],
      body: section.rows,
      theme: "striped",
      styles: { fontSize: 8, cellPadding: 4, overflow: "linebreak" },
      headStyles: { fillColor: [244, 244, 248], textColor: 30, fontStyle: "bold" },
      alternateRowStyles: { fillColor: [252, 252, 253] },
      columnStyles,
      margin: { left: margin, right: margin },
    });
    y = ((doc as unknown as { lastAutoTable?: { finalY?: number } }).lastAutoTable?.finalY ?? y) + 26;
  }

  // ---- Page numbers -------------------------------------------------------
  const pages = doc.getNumberOfPages();
  const pageH = doc.internal.pageSize.getHeight();
  for (let i = 1; i <= pages; i++) {
    doc.setPage(i);
    doc.setFont("helvetica", "normal").setFontSize(8).setTextColor(140);
    doc.text(`Page ${i} of ${pages}`, pageW - margin, pageH - 16, { align: "right" });
    doc.text(`${report.business.name} · ${report.title}`, margin, pageH - 16);
  }

  doc.save(report.fileName);
}

function renderCsv(report: BusinessReport) {
  const lines: string[] = [
    [report.business.name, report.title].map(csvCell).join(","),
    [`${report.periodLabel}`, report.rangeLabel].map(csvCell).join(","),
    [`Amounts in ${report.business.currency}`].map(csvCell).join(","),
    "",
  ];
  for (const s of report.summary) lines.push([s.label, s.value].map(csvCell).join(","));
  for (const section of report.sections) {
    lines.push("", section.title);
    lines.push(section.columns.map(csvCell).join(","));
    for (const row of section.rows) lines.push(row.map(csvCell).join(","));
  }
  downloadBlob(lines.join("\n"), report.fileName.replace(/\.pdf$/, ".csv"), "text/csv;charset=utf-8");
}

export function ReportDownload() {
  const [type, setType] = useState<ReportType>("consolidated");
  const [preset, setPreset] = useState<PeriodPreset>("month");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [pending, start] = useTransition();

  function run(format: "pdf" | "csv") {
    setError(null);
    setNote(null);
    start(async () => {
      try {
        const report = await buildReportAction({ type, preset, from, to });
        if (report.empty) {
          setNote("No records found for that period, so nothing was downloaded.");
          return;
        }
        if (format === "pdf") await renderPdf(report);
        else renderCsv(report);
        setNote(`Downloaded ${report.fileName.replace(/\.pdf$/, format === "pdf" ? ".pdf" : ".csv")}`);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not build that report.");
      }
    });
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Report">
          <Select value={type} onChange={(e) => setType(e.target.value as ReportType)}>
            {TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Period">
          <Select value={preset} onChange={(e) => setPreset(e.target.value as PeriodPreset)}>
            {PERIODS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      {preset === "custom" && (
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="From">
            <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
          </Field>
          <Field label="To">
            <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
          </Field>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={() => run("pdf")} disabled={pending}>
          <Icon name="reports" size={16} /> {pending ? "Preparing…" : "Download PDF"}
        </Button>
        <Button variant="outline" onClick={() => run("csv")} disabled={pending}>
          Download CSV
        </Button>
      </div>

      {note && <p className="text-sm text-muted-foreground">{note}</p>}
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
