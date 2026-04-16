import { NextRequest, NextResponse } from "next/server";

const base = () => process.env.API_URL ?? "http://localhost:8000";

// POST → discover & upsert repos for this org, returns { added, total }
export async function POST(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  const upstream = await fetch(`${base()}/orgs/${id}/discover-repos`, {
    method: "POST",
  });
  return NextResponse.json(await upstream.json(), { status: upstream.status });
}
