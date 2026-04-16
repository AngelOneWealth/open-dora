import { NextRequest, NextResponse } from "next/server";

const base = () => process.env.API_URL ?? "http://localhost:8000";

// POST → start sync job, returns { job_id } with 202
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const body = await req.json().catch(() => ({}));
  const phases = body.phases ?? "all";

  const upstream = await fetch(`${base()}/repos/${id}/sync?phases=${phases}`, {
    method: "POST",
  });
  return NextResponse.json(await upstream.json(), { status: upstream.status });
}

// GET ?job_id=... → pipe NDJSON stream from the running job
export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const jobId = req.nextUrl.searchParams.get("job_id");
  if (!jobId) {
    return NextResponse.json({ error: "missing job_id" }, { status: 400 });
  }

  const upstream = await fetch(`${base()}/repos/${id}/sync/${jobId}/stream`);
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "Content-Type": "application/x-ndjson" },
  });
}
