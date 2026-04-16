import ReposList from "./ReposList";

type Repo = {
  id: number;
  owner: string;
  name: string;
  full_name: string;
  default_branch: string;
  commits: number;
  net_lines: number;
  prs_opened: number;
  reviews: number;
  contributors: number;
  commits_synced_at: string | null;
  prs_synced_at: string | null;
  reviews_synced_at: string | null;
  pr_commits_synced_at: string | null;
};

async function getRepos(): Promise<{ repos: Repo[]; total: number }> {
  const base = process.env.API_URL ?? "http://localhost:8000";
  const res = await fetch(`${base}/repos?limit=200`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch repos");
  return res.json();
}

export default async function ReposPage() {
  const { repos, total } = await getRepos();

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-6xl mx-auto">
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-gray-900">Repositories</h1>
          <p className="text-sm text-gray-500 mt-1">{total} total</p>
        </div>

        <ReposList repos={repos} />
      </div>
    </main>
  );
}
