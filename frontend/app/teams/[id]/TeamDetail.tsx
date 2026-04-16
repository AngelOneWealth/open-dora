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

export type TeamDetailData = {
  id: number;
  name: string;
  start_date: string;
  end_date: string;
  members: UserStatRow[];
  totals: UserStatRow;
  weekly: WeeklyUserStat[];
};

export default function TeamDetail({ data }: { data: TeamDetailData }) {
  const series: Series[] = data.members.map((m) => ({
    id: m.id,
    label: m.full_name ?? m.name ?? m.login,
    sublabel: `@${m.login}`,
    avatar_url: m.avatar_url,
    href: `/users/${m.id}`,
  }));

  const weekly: WeeklyStat[] = data.weekly.map((w) => ({
    week_start: w.week_start,
    series_id: w.user_id,
    commits: w.commits,
    net_lines: w.net_lines,
  }));

  const rows: StatRow[] = data.members.map((m) => ({
    series_id: m.id,
    commits: m.commits,
    additions: m.additions,
    deletions: m.deletions,
    prs_opened: m.prs_opened,
    prs_merged: m.prs_merged,
    reviews: m.reviews,
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
      basePath={`/teams/${data.id}`}
      chartTitle="Weekly activity — all members"
      firstColLabel="User"
      defaultSortKey="commits"
      defaultSortDir="desc"
    />
  );
}
