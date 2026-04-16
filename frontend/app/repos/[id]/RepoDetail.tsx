import StatsPanel, { type Series, type WeeklyStat, type StatRow, type Totals } from "@/app/components/StatsPanel";

type UserStatRow = {
  id: number;
  login: string;
  name: string | null;
  full_name: string | null;
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

export type RepoDetailData = {
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

export default function RepoDetail({ data }: { data: RepoDetailData }) {
  const series: Series[] = data.contributors.map((c) => ({
    id: c.id,
    label: c.full_name ?? c.name ?? c.login,
    sublabel: `@${c.login}`,
    avatar_url: c.avatar_url,
    href: `/users/${c.id}`,
  }));

  const weekly: WeeklyStat[] = data.weekly.map((w) => ({
    week_start: w.week_start,
    series_id: w.user_id,
    commits: w.commits,
    net_lines: w.net_lines,
  }));

  const rows: StatRow[] = data.contributors.map((c) => ({
    series_id: c.id,
    commits: c.commits,
    additions: c.additions,
    deletions: c.deletions,
    prs_opened: c.prs_opened,
    prs_merged: c.prs_merged,
    reviews: c.reviews,
  }));

  const totals: Totals = {
    commits: data.totals.commits,
    additions: data.totals.additions,
    deletions: data.totals.deletions,
    prs_opened: data.totals.prs_opened,
    prs_merged: data.totals.prs_merged,
    reviews: data.totals.reviews,
  };

  return (
    <StatsPanel
      series={series}
      weekly={weekly}
      rows={rows}
      totals={totals}
      startDate={data.start_date}
      endDate={data.end_date}
      basePath={`/repos/${data.id}`}
      chartTitle="Weekly activity — all contributors"
      firstColLabel="Contributor"
      defaultSortKey="commits"
      defaultSortDir="desc"
    />
  );
}
