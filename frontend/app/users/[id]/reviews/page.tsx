import { notFound } from "next/navigation";
import Link from "next/link";

const BASE = process.env.API_URL ?? "http://localhost:8000";

type ReviewItem = {
  id: number;
  state: string;
  submitted_at: string;
  pr_number: number;
  pr_title: string;
  pr_state: string;
  repo_full_name: string;
  github_url: string;
  pr_author_login: string | null;
  pr_author_name: string | null;
  pr_author_avatar_url: string | null;
};

type User = { id: number; login: string; name: string | null; full_name: string | null; avatar_url: string | null };

function fmtDate(iso: string) {
  const d = new Date(iso);
  const day   = String(d.getDate()).padStart(2, "0");
  const month = d.toLocaleDateString("en-US", { month: "short" });
  return `${day} ${month}, ${d.getFullYear()}`;
}

function ReviewStateBadge({ state }: { state: string }) {
  const styles: Record<string, string> = {
    approved:           "bg-green-100  text-green-700",
    changes_requested:  "bg-orange-100 text-orange-700",
    commented:          "bg-blue-100   text-blue-700",
    dismissed:          "bg-gray-100   text-gray-500",
  };
  const labels: Record<string, string> = {
    approved:           "Approved",
    changes_requested:  "Changes requested",
    commented:          "Commented",
    dismissed:          "Dismissed",
  };
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium whitespace-nowrap ${styles[state] ?? "bg-gray-100 text-gray-600"}`}>
      {labels[state] ?? state}
    </span>
  );
}

function PRStateBadge({ state }: { state: string }) {
  const styles: Record<string, string> = {
    open:   "bg-green-100  text-green-700",
    merged: "bg-purple-100 text-purple-700",
    closed: "bg-red-100    text-red-600",
  };
  return (
    <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${styles[state] ?? "bg-gray-100 text-gray-600"}`}>
      {state}
    </span>
  );
}

export default async function UserReviewsPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ start_date?: string; end_date?: string }>;
}) {
  const { id } = await params;
  const { start_date, end_date } = await searchParams;

  const end   = end_date   ?? new Date().toISOString().slice(0, 10);
  const start = start_date ?? new Date(Date.now() - 180 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);

  const [userRes, reviewsRes] = await Promise.all([
    fetch(`${BASE}/users/${id}?start_date=${start}&end_date=${end}`, { cache: "no-store" }),
    fetch(`${BASE}/users/${id}/reviews?start_date=${start}&end_date=${end}`, { cache: "no-store" }),
  ]);

  if (userRes.status === 404) notFound();
  const user: User = await userRes.json();
  const { reviews }: { reviews: ReviewItem[] } = reviewsRes.ok ? await reviewsRes.json() : { reviews: [] };

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-5xl mx-auto">
        {/* Breadcrumb */}
        <div className="mb-1">
          <Link href={`/users/${id}`} className="text-sm text-blue-600 hover:underline">
            ← {user.full_name ?? user.name ?? user.login}
          </Link>
        </div>
        <h1 className="text-3xl font-bold text-gray-900 mb-1">Reviews</h1>
        <p className="text-sm text-gray-500 mb-6">
          {fmtDate(start)} – {fmtDate(end)}
        </p>

        {/* Table */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-x-auto">
          {reviews.length === 0 ? (
            <p className="py-12 text-center text-sm text-gray-400">No reviews found.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Pull Request</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Author</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Repository</th>
                  <th className="text-center px-4 py-3 font-medium text-gray-600">PR State</th>
                  <th className="text-center px-4 py-3 font-medium text-gray-600">Review</th>
                  <th className="text-right px-4 py-3 font-medium text-gray-600">Reviewed</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {reviews.map((r) => (
                  <tr key={r.id} className="hover:bg-blue-50 transition-colors">
                    <td className="px-4 py-3 max-w-sm">
                      <a
                        href={r.github_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 hover:underline font-medium line-clamp-1"
                        title={r.pr_title}
                      >
                        #{r.pr_number} {r.pr_title}
                      </a>
                    </td>
                    <td className="px-4 py-3">
                      {r.pr_author_login ? (
                        <Link href={`/users?search=${r.pr_author_login}`} className="flex items-center gap-2 group">
                          {r.pr_author_avatar_url ? (
                            <img src={r.pr_author_avatar_url} alt={r.pr_author_login} className="w-6 h-6 rounded-full flex-shrink-0" />
                          ) : (
                            <div className="w-6 h-6 rounded-full bg-gray-200 flex items-center justify-center text-xs font-medium text-gray-500 flex-shrink-0">
                              {r.pr_author_login[0]?.toUpperCase()}
                            </div>
                          )}
                          <span className="text-sm text-gray-700 group-hover:text-blue-600 group-hover:underline whitespace-nowrap">
                            {r.pr_author_name ?? r.pr_author_login}
                          </span>
                        </Link>
                      ) : (
                        <span className="text-gray-400 text-xs">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{r.repo_full_name}</td>
                    <td className="px-4 py-3 text-center">
                      <PRStateBadge state={r.pr_state} />
                    </td>
                    <td className="px-4 py-3 text-center">
                      <ReviewStateBadge state={r.state} />
                    </td>
                    <td className="px-4 py-3 text-right text-gray-600 text-xs tabular-nums whitespace-nowrap">
                      {fmtDate(r.submitted_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <p className="mt-3 text-xs text-gray-400 text-right">{reviews.length} review{reviews.length !== 1 ? "s" : ""}</p>
      </div>
    </main>
  );
}
