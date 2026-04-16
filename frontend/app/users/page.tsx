import UsersList from "./UsersList";

type User = {
  id: number;
  login: string;
  name: string | null;
  avatar_url: string | null;
  email: string | null;
  active: boolean;
  team_id: number | null;
  team_name: string | null;
  commits: number;
  net_lines: number;
  prs_opened: number;
  reviews: number;
};

type Team = {
  id: number;
  name: string;
};

const BASE = process.env.API_URL ?? "http://localhost:8000";

async function getUsers(active: boolean): Promise<{ users: User[]; total: number }> {
  const res = await fetch(`${BASE}/users?limit=500&active=${active}`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch users");
  return res.json();
}

async function getTeams(): Promise<{ teams: Team[]; total: number }> {
  const res = await fetch(`${BASE}/teams`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch teams");
  return res.json();
}

export default async function UsersPage() {
  const [{ users: activeUsers }, { users: inactiveUsers }, { teams }] = await Promise.all([
    getUsers(true),
    getUsers(false),
    getTeams(),
  ]);

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-5xl mx-auto">
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-gray-900">Users</h1>
        </div>

        <UsersList activeUsers={activeUsers} inactiveUsers={inactiveUsers} teams={teams} />
      </div>
    </main>
  );
}
