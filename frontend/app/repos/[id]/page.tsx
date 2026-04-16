import { notFound } from "next/navigation";
import RepoDetail from "./RepoDetail";

type UserStatRow = {
  id: number;
  login: string;
  name: string | null;
  avatar_url: string | null;
  commits: number;
  additions: number;
  deletions: number;
  prs_opened: number;
  prs_merged: number;
  reviews: number;
};

type WeeklyUserStat = {
  week_start: string;
  user_id: number;
  commits: number;
  net_lines: number;
};

type RepoDetailData = {
  id: number;
  owner: string;
  name: string;
  full_name: string;
  default_branch: string;
  start_date: string;
  end_date: string;
  contributors: UserStatRow[];
  totals: UserStatRow;
  weekly: WeeklyUserStat[];
};

const BASE = process.env.API_URL ?? "http://localhost:8000";

export default async function RepoDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ start_date?: string; end_date?: string }>;
}) {
  const { id } = await params;
  const { start_date, end_date } = await searchParams;

  const today = new Date();
  const endDefault = today.toISOString().slice(0, 10);
  const startDefault = new Date(today.getTime() - 180 * 24 * 60 * 60 * 1000)
    .toISOString()
    .slice(0, 10);

  const sd = start_date ?? startDefault;
  const ed = end_date ?? endDefault;

  const res = await fetch(
    `${BASE}/repos/${id}?start_date=${sd}&end_date=${ed}`,
    { cache: "no-store" }
  );

  if (!res.ok) notFound();
  const data: RepoDetailData = await res.json();

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-6xl mx-auto">
        <div className="mb-6">
          <a href="/repos" className="text-sm text-gray-500 hover:text-gray-700">
            ← Repositories
          </a>
          <h1 className="text-3xl font-bold text-gray-900 mt-2">{data.full_name}</h1>
          <p className="text-sm text-gray-500 mt-1">
            {data.contributors.length} contributor{data.contributors.length !== 1 ? "s" : ""}
            {" · "}branch: {data.default_branch}
          </p>
        </div>

        <RepoDetail data={data} />
      </div>
    </main>
  );
}
