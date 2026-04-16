import OrgsList from "./OrgsList";

const BASE = process.env.API_URL ?? "http://localhost:8000";

type Org = {
  id: number;
  login: string;
  display_name: string | null;
  avatar_url: string | null;
  token_preview: string;
  repo_count: number;
  created_at: string;
};

async function getOrgs(): Promise<{ orgs: Org[] }> {
  const res = await fetch(`${BASE}/orgs`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch organisations");
  return res.json();
}

export default async function OrgsPage() {
  const { orgs } = await getOrgs();

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-4xl mx-auto">
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-gray-900">Organisations</h1>
          <p className="text-sm text-gray-500 mt-1">
            {orgs.length} configured · GitHub tokens are stored per org and never shown in full
          </p>
        </div>

        <OrgsList orgs={orgs} />
      </div>
    </main>
  );
}
