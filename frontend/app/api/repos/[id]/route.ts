import { NextRequest, NextResponse } from "next/server";

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const base = process.env.API_URL ?? "http://localhost:8000";
  const res = await fetch(`${base}/repos/${id}`, { method: "DELETE" });
  return NextResponse.json(await res.json(), { status: res.status });
}
