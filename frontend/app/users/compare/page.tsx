import { notFound } from "next/navigation";
import Link from "next/link";
import StatsPanel, { type Series, type WeeklyStat, type StatRow, type Totals } from "@/app/components/StatsPanel";

const BASE = process.env.API_URL ?? "http://localhost:8000";

type WeekActivity = {
  week_start: string;
  commits: number;
  additions: number;
  deletions: number;
  prs_opened: number;
  prs_merged: number;
  reviews: number;
};

type ActivityTotals = {
  commits: number;
  additions: number;
  deletions: number;
  prs_opened: number;
  prs_merged: number;
  reviews: number;
};

type UserDetail = {
  id: number;
  login: string;
  name: string | null;
  full_name: string | null;
  avatar_url: string | null;
  weeks: WeekActivity[];
  totals: ActivityTotals;
};

async function fetchUser(id: number, start: string, end: string): Promise<UserDetail | null> {
  try {
    const res = await fetch(
      `${BASE}/users/${id}?start_date=${start}&end_date=${end}`,
      { cache: "no-store" }
    );
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function ComparePage({
  searchParams,
}: {
  searchParams: Promise<{ ids?: string; start_date?: string; end_date?: string }>;
}) {
  const params = await searchParams;

  const ids = (params.ids ?? "")
    .split(",")
    .map(Number)
    .filter((n) => n > 0);

  if (ids.length < 2) notFound();

  const end   = params.end_date   ?? new Date().toISOString().slice(0, 10);
  const start = params.start_date ?? new Date(Date.now() - 180 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);

  const users = (await Promise.all(ids.map((id) => fetchUser(id, start, end)))).filter(
    (u): u is UserDetail => u !== null
  );

  if (users.length < 2) notFound();

  // ── Map to StatsPanel shapes ──────────────────────────────────────────────

  const series: Series[] = users.map((u) => ({
    id:        u.id,
    label:     u.full_name ?? u.name ?? u.login,
    sublabel:  `@${u.login}`,
    avatar_url: u.avatar_url ?? null,
    href:      `/users/${u.id}`,
  }));

  // Use per-user weekly totals (not per-repo) for the comparison chart
  const weekly: WeeklyStat[] = users.flatMap((u) =>
    u.weeks.map((w) => ({
      week_start: typeof w.week_start === "string" ? w.week_start : String(w.week_start),
      series_id:  u.id,
      commits:    w.commits,
      net_lines:  w.additions - w.deletions,
    }))
  );

  const rows: StatRow[] = users.map((u) => ({
    series_id:  u.id,
    commits:    u.totals.commits,
    additions:  u.totals.additions,
    deletions:  u.totals.deletions,
    prs_opened: u.totals.prs_opened,
    prs_merged: u.totals.prs_merged,
    reviews:    u.totals.reviews,
  }));

  const totals: Totals = {
    commits:    rows.reduce((s, r) => s + r.commits,    0),
    additions:  rows.reduce((s, r) => s + r.additions,  0),
    deletions:  rows.reduce((s, r) => s + r.deletions,  0),
    prs_opened: rows.reduce((s, r) => s + r.prs_opened, 0),
    prs_merged: rows.reduce((s, r) => s + r.prs_merged, 0),
    reviews:    rows.reduce((s, r) => s + r.reviews,    0),
  };

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <Link href="/users" className="text-sm text-blue-600 hover:underline">
            ← Users
          </Link>
          <h1 className="text-3xl font-bold text-gray-900 mt-2">Compare Users</h1>
          <div className="mt-2 flex items-center gap-3 flex-wrap">
            {users.map((u) => (
              <Link
                key={u.id}
                href={`/users/${u.id}`}
                className="inline-flex items-center gap-1.5 text-sm text-gray-600 hover:text-blue-600 hover:underline"
              >
                {u.avatar_url ? (
                  <img src={u.avatar_url} alt={u.login} className="w-5 h-5 rounded-full" />
                ) : (
                  <div className="w-5 h-5 rounded-full bg-gray-200 flex items-center justify-center text-xs font-medium text-gray-500">
                    {(u.full_name ?? u.name ?? u.login)[0].toUpperCase()}
                  </div>
                )}
                {u.full_name ?? u.name ?? u.login}
              </Link>
            ))}
          </div>
        </div>

        {/* Stats panel — one line per user */}
        <StatsPanel
          series={series}
          weekly={weekly}
          rows={rows}
          totals={totals}
          startDate={start}
          endDate={end}
          basePath={`/users/compare?ids=${ids.join(",")}`}
          chartTitle="Weekly activity by user"
          firstColLabel="User"
          defaultSortKey="commits"
          defaultSortDir="desc"
        />
      </div>
    </main>
  );
}
