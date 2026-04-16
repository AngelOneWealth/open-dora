import { notFound } from "next/navigation";
import Link from "next/link";
import StatsPanel, { type Series, type WeeklyStat, type StatRow } from "@/app/components/StatsPanel";
import EditableName from "./EditableName";

type WeekActivity = {
  week_start: string;
  commits: number;
  additions: number;
  deletions: number;
  prs_opened: number;
  prs_merged: number;
  reviews: number;
};

type RepoStatRow = {
  repo_id: number;
  repo_name: string;
  commits: number;
  additions: number;
  deletions: number;
  prs_opened: number;
  prs_merged: number;
  reviews: number;
};

type WeeklyRepoStat = {
  week_start: string;
  repo_id: number;
  commits: number;
  net_lines: number;
};

type UserDetail = {
  id: number;
  login: string;
  name: string | null;
  full_name: string | null;
  email: string | null;
  avatar_url: string | null;
  start_date: string;
  end_date: string;
  weeks: WeekActivity[];
  totals: {
    commits: number;
    additions: number;
    deletions: number;
    prs_opened: number;
    prs_merged: number;
    reviews: number;
  };
  repos: RepoStatRow[];
  weekly_by_repo: WeeklyRepoStat[];
};

function defaultDates() {
  const end = new Date();
  const start = new Date();
  start.setMonth(start.getMonth() - 6);
  return {
    start: start.toISOString().split("T")[0],
    end: end.toISOString().split("T")[0],
  };
}

async function getUserDetail(
  userId: string,
  startDate: string,
  endDate: string
): Promise<UserDetail | null> {
  const base = process.env.API_URL ?? "http://localhost:8000";
  const res = await fetch(
    `${base}/users/${userId}?start_date=${startDate}&end_date=${endDate}`,
    { cache: "no-store" }
  );
  if (res.status === 404) return null;
  if (!res.ok) throw new Error("Failed to fetch user");
  return res.json();
}

function statCards(totals: UserDetail["totals"], userId: number, startDate: string, endDate: string) {
  const dateSuffix = `start_date=${startDate}&end_date=${endDate}`;
  return [
    {
      label: "Commits",
      value: totals.commits,
    },
    { label: "Lines added",   value: totals.additions },
    { label: "Lines removed", value: totals.deletions },
    { label: "Net lines",     value: totals.additions - totals.deletions },
    {
      label: "PRs opened",
      value: totals.prs_opened,
      href: `/users/${userId}/prs?${dateSuffix}`,
    },
    {
      label: "PRs merged",
      value: totals.prs_merged,
      href: `/users/${userId}/prs?status=merged&${dateSuffix}`,
    },
    {
      label: "Reviews",
      value: totals.reviews,
      href: `/users/${userId}/reviews?${dateSuffix}`,
    },
  ];
}

export default async function UserPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ start_date?: string; end_date?: string }>;
}) {
  const { id } = await params;
  const { start_date, end_date } = await searchParams;
  const defaults = defaultDates();
  const startDate = start_date ?? defaults.start;
  const endDate = end_date ?? defaults.end;

  const user = await getUserDetail(id, startDate, endDate);
  if (!user) notFound();

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <a href="/users" className="text-sm text-gray-500 hover:text-gray-700">
            ← Users
          </a>
          <div className="flex items-center gap-4 mt-3">
            {user.avatar_url ? (
              <img
                src={user.avatar_url}
                alt={user.login}
                className="w-14 h-14 rounded-full"
              />
            ) : (
              <div className="w-14 h-14 rounded-full bg-gray-200 flex items-center justify-center text-gray-500 font-bold text-xl">
                {(user.full_name ?? user.name ?? user.login[0]).toUpperCase()}
              </div>
            )}
            <div>
              <EditableName
                userId={user.id}
                fullName={user.full_name}
                fallback={user.name ?? user.login}
              />
              <p className="text-gray-500 mt-0.5">@{user.login}</p>
              {user.email && (
                <p className="text-sm text-gray-400">{user.email}</p>
              )}
            </div>
          </div>
        </div>

        {/* Stat cards */}
        <div className="grid grid-cols-4 gap-3 mb-6">
          {statCards(user.totals, user.id, startDate, endDate).map(({ label, value, href }) => {
            const inner = (
              <>
                <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
                <p className="text-2xl font-bold text-gray-900 mt-1">
                  {value.toLocaleString("en-US")}
                </p>
                {href && (
                  <p className="text-xs text-blue-500 mt-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    View details →
                  </p>
                )}
              </>
            );
            return href ? (
              <Link
                key={label}
                href={href}
                className="group bg-white rounded-xl border border-gray-200 p-4 hover:border-blue-400 hover:shadow-sm transition-all"
              >
                {inner}
              </Link>
            ) : (
              <div key={label} className="bg-white rounded-xl border border-gray-200 p-4">
                {inner}
              </div>
            );
          })}
        </div>

        {/* Chart + per-repo table */}
        <div className="mt-6">
          <StatsPanel
            series={user.repos.map((r): Series => ({
              id: r.repo_id,
              label: r.repo_name.split("/").pop() ?? r.repo_name,
              sublabel: r.repo_name,
              href: `/repos/${r.repo_id}`,
            }))}
            weekly={user.weekly_by_repo.map((w): WeeklyStat => ({
              week_start: w.week_start,
              series_id: w.repo_id,
              commits: w.commits,
              net_lines: w.net_lines,
            }))}
            rows={user.repos.map((r): StatRow => ({
              series_id: r.repo_id,
              commits: r.commits,
              additions: r.additions,
              deletions: r.deletions,
              prs_opened: r.prs_opened,
              prs_merged: r.prs_merged,
              reviews: r.reviews,
            }))}
            totals={user.totals}
            startDate={startDate}
            endDate={endDate}
            basePath={`/users/${id}`}
            chartTitle="Weekly activity by repository"
            firstColLabel="Repository"
            defaultSortKey="commits"
            defaultSortDir="desc"
          />
        </div>
      </div>
    </main>
  );
}
