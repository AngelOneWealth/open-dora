import MissingUsersList from "./MissingUsersList";

type MissingAuthor = {
  author_name: string | null;
  author_email: string | null;
  commit_count: number;
};

type User = {
  id: number;
  login: string;
  name: string | null;
  full_name: string | null;
};

async function getMissingAuthors(): Promise<{ authors: MissingAuthor[]; total: number }> {
  const base = process.env.API_URL ?? "http://localhost:8000";
  const res = await fetch(`${base}/users/missing?limit=500`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch missing authors");
  return res.json();
}

async function getUsers(): Promise<{ users: User[] }> {
  const base = process.env.API_URL ?? "http://localhost:8000";
  const res = await fetch(`${base}/users?limit=500`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to fetch users");
  return res.json();
}

export default async function MissingUsersPage() {
  const [{ authors, total }, { users }] = await Promise.all([
    getMissingAuthors(),
    getUsers(),
  ]);

  const sortedUsers = [...users].sort((a, b) => a.login.localeCompare(b.login));

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-5xl mx-auto">
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-gray-900">Missing Users</h1>
          <p className="text-sm text-gray-500 mt-1">
            {total} distinct git {total === 1 ? "identity" : "identities"} with no linked GitHub account
          </p>
        </div>

        <MissingUsersList authors={authors} total={total} users={sortedUsers} />
      </div>
    </main>
  );
}
