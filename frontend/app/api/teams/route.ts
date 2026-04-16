import { NextRequest, NextResponse } from "next/server";

const BASE = process.env.API_URL ?? "http://localhost:8000";

export async function GET() {
  const res = await fetch(`${BASE}/teams`, { cache: "no-store" });
  return NextResponse.json(await res.json(), { status: res.status });
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const res = await fetch(`${BASE}/teams`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return NextResponse.json(await res.json(), { status: res.status });
}
