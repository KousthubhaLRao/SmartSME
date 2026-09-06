"use server";

import { requireUser } from "@/lib/auth/current-user";
import { getRevenueSeries, type RevenuePoint } from "@/lib/analytics";
import { buildReport, type BusinessReport, type PeriodPreset, type ReportType } from "@/lib/reports";

const ALLOWED = new Set([7, 30, 90, 180, 365]);

export async function getRevenueSeriesAction(days: number): Promise<RevenuePoint[]> {
  const { business } = await requireUser();
  const d = ALLOWED.has(days) ? days : 30;
  return getRevenueSeries(business.id, d);
}

/** Builds a downloadable business report for the chosen type + period. */
export async function buildReportAction(input: {
  type: ReportType;
  preset: PeriodPreset;
  from?: string;
  to?: string;
}): Promise<BusinessReport> {
  const { business } = await requireUser();
  return buildReport(business.id, input);
}
