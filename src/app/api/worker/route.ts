import { NextResponse } from "next/server";
import { ensureReady } from "@/db";
import { drainQueue } from "@/worker/loop";

export const dynamic = "force-dynamic";

// Drains any pending events. Business writes already drain synchronously, so
// this is a backstop for scheduled processing (e.g. a Vercel Cron hitting
// /api/worker) or retrying dead-lettered events. If CRON_SECRET is set, callers
// must send `Authorization: Bearer <CRON_SECRET>`.
async function handle(request: Request): Promise<Response> {
  const secret = process.env.CRON_SECRET;
  if (secret) {
    const auth = request.headers.get("authorization");
    if (auth !== `Bearer ${secret}`) {
      return NextResponse.json({ error: "unauthorized" }, { status: 401 });
    }
  }
  await ensureReady();
  const processed = await drainQueue();
  return NextResponse.json({ ok: true, processed });
}

export const GET = handle;
export const POST = handle;
