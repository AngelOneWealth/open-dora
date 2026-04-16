import TeamsList from "./TeamsList";

type Team = {
  id: number;
  name: string;
  created_at: string;
  member_count: number;
  commits: number;
  net_lines: number;
  prs_opened: number;
  reviews: number;
};

async function getTeams(): Promise<{ teams: Team[]; total: number }> {
  const base = process.env.API_URL ?? "http://localhost:8000";
  const res = await fetch(`${base}/teams`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch teams");
  return res.json();
}

export default async function TeamsPage() {
  const { teams, total } = await getTeams();

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-5xl mx-auto">
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-gray-900">Teams</h1>
          <p className="text-sm text-gray-500 mt-1">{total} {total === 1 ? "team" : "teams"}</p>
        </div>

        <TeamsList teams={teams} />
      </div>
    </main>
  );
}
