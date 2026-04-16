import { notFound } from "next/navigation";
import Link from "next/link";

const BASE = process.env.API_URL ?? "http://localhost:8000";

type ReviewerInfo = {
  id: number;
  login: string;
  name: string | null;
  full_name: string | null;
  avatar_url: string | null;
  state: string;
};

type PRItem = {
  id: number;
  number: number;
  title: string;
  state: string;
  repo_full_name: string;
  github_url: string;
  opened_at: string;
  merged_at: string | null;
  closed_at: string | null;
  additions: number;
  deletions: number;
  changed_files: number;
  commits_count: number;
  reviewers: ReviewerInfo[];
};

type User = { id: number; login: string; name: string | null; full_name: string | null; avatar_url: string | null };

function fmtDate(iso: string) {
  const d = new Date(iso);
  const day   = String(d.getDate()).padStart(2, "0");
  const month = d.toLocaleDateString("en-US", { month: "short" });
  return `${day} ${month}, ${d.getFullYear()}`;
}

function fmt(n: number) { return n.toLocaleString("en-US"); }

function StateBadge({ state }: { state: string }) {
  const styles: Record<string, string> = {
    open:   "bg-green-100 text-green-700",
    merged: "bg-purple-100 text-purple-700",
    closed: "bg-red-100   text-red-600",
  };
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${styles[state] ?? "bg-gray-100 text-gray-600"}`}>
      {state}
    </span>
  );
}

const REVIEW_RING: Record<string, string> = {
  approved:           "ring-green-400",
  changes_requested:  "ring-orange-400",
  commented:          "ring-blue-300",
  dismissed:          "ring-gray-300",
};

function ReviewerAvatars({ reviewers }: { reviewers: ReviewerInfo[] }) {
  if (reviewers.length === 0)
    return <span className="text-gray-300 text-xs">—</span>;

  const visible  = reviewers.slice(0, 4);
  const overflow = reviewers.length - visible.length;

  return (
    <div className="flex items-center gap-1 flex-wrap">
      {visible.map((r) => (
        <span
          key={r.id}
          title={`${r.full_name ?? r.name ?? r.login} · ${r.state.replace(/_/g, " ")}`}
          className={`ring-2 ${REVIEW_RING[r.state] ?? "ring-gray-300"} rounded-full`}
        >
          {r.avatar_url ? (
            <img
              src={r.avatar_url}
              alt={r.login}
              className="w-6 h-6 rounded-full block"
            />
          ) : (
            <div className="w-6 h-6 rounded-full bg-gray-200 flex items-center justify-center text-xs font-medium text-gray-500">
              {(r.full_name ?? r.name ?? r.login)[0].toUpperCase()}
            </div>
          )}
        </span>
      ))}
      {overflow > 0 && (
        <span className="text-xs text-gray-400">+{overflow}</span>
      )}
    </div>
  );
}

export default async function UserPRsPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ status?: string; start_date?: string; end_date?: string }>;
}) {
  const { id } = await params;
  const { status, start_date, end_date } = await searchParams;

  const end   = end_date   ?? new Date().toISOString().slice(0, 10);
  const start = start_date ?? new Date(Date.now() - 180 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
  const statusParam = status ?? "all";

  // Fetch user info and PRs in parallel
  const [userRes, prsRes] = await Promise.all([
    fetch(`${BASE}/users/${id}?start_date=${start}&end_date=${end}`, { cache: "no-store" }),
    fetch(
      `${BASE}/users/${id}/prs?start_date=${start}&end_date=${end}${statusParam !== "all" ? `&status=${statusParam}` : ""}`,
      { cache: "no-store" }
    ),
  ]);

  if (userRes.status === 404) notFound();
  const user: User = await userRes.json();
  const { prs }: { prs: PRItem[] } = prsRes.ok ? await prsRes.json() : { prs: [] };

  // ── Aggregate reviewer stats from existing PR data (no extra fetch) ─────────
  type ReviewerSummary = {
    id: number; login: string; name: string | null; full_name: string | null; avatar_url: string | null;
    prs_reviewed: number; approved: number; changes_requested: number;
    commented: number; dismissed: number;
  };
  const reviewerMap = new Map<number, ReviewerSummary>();
  for (const pr of prs) {
    for (const r of pr.reviewers) {
      if (!reviewerMap.has(r.id)) {
        reviewerMap.set(r.id, {
          id: r.id, login: r.login, name: r.name, full_name: r.full_name, avatar_url: r.avatar_url,
          prs_reviewed: 0, approved: 0, changes_requested: 0, commented: 0, dismissed: 0,
        });
      }
      const s = reviewerMap.get(r.id)!;
      s.prs_reviewed++;
      if (r.state === "approved")               s.approved++;
      else if (r.state === "changes_requested") s.changes_requested++;
      else if (r.state === "commented")         s.commented++;
      else if (r.state === "dismissed")         s.dismissed++;
    }
  }
  const reviewerStats = [...reviewerMap.values()].sort(
    (a, b) => b.prs_reviewed - a.prs_reviewed
  );

  const STATUSES = ["all", "open", "merged", "closed"] as const;

  function tabHref(s: string) {
    const p = new URLSearchParams({ start_date: start, end_date: end });
    if (s !== "all") p.set("status", s);
    return `/users/${id}/prs?${p}`;
  }

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-6xl mx-auto">
        {/* Breadcrumb */}
        <div className="mb-1">
          <Link href={`/users/${id}`} className="text-sm text-blue-600 hover:underline">
            ← {user.full_name ?? user.name ?? user.login}
          </Link>
        </div>
        <h1 className="text-3xl font-bold text-gray-900 mb-1">Pull Requests</h1>
        <p className="text-sm text-gray-500 mb-6">
          {fmtDate(start)} – {fmtDate(end)}
        </p>

        {/* Reviewer summary */}
        {reviewerStats.length > 0 && (
          <div className="mb-6">
            <h2 className="text-base font-semibold text-gray-800 mb-3">Reviewers</h2>
            <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <th className="text-left px-4 py-3 font-medium text-gray-600">Reviewer</th>
                    <th className="text-right px-4 py-3 font-medium text-gray-600">PRs Reviewed</th>
                    <th className="text-right px-4 py-3 font-medium text-green-600">Approved</th>
                    <th className="text-right px-4 py-3 font-medium text-orange-500">Changes Requested</th>
                    <th className="text-right px-4 py-3 font-medium text-blue-500">Commented</th>
                    <th className="text-right px-4 py-3 font-medium text-gray-400">Dismissed</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {reviewerStats.map((r) => (
                    <tr key={r.id} className="hover:bg-blue-50 transition-colors">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          {r.avatar_url ? (
                            <img src={r.avatar_url} alt={r.login} className="w-7 h-7 rounded-full" />
                          ) : (
                            <div className="w-7 h-7 rounded-full bg-gray-200 flex items-center justify-center text-xs font-medium text-gray-500">
                              {(r.full_name ?? r.name ?? r.login)[0].toUpperCase()}
                            </div>
                          )}
                          <div>
                            <div className="font-medium text-gray-900">{r.full_name ?? r.name ?? r.login}</div>
                            <div className="text-xs text-gray-400">@{r.login}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right text-gray-700 tabular-nums font-medium">
                        {r.prs_reviewed}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        {r.approved > 0
                          ? <span className="text-green-600 font-medium">{r.approved}</span>
                          : <span className="text-gray-300">—</span>}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        {r.changes_requested > 0
                          ? <span className="text-orange-500 font-medium">{r.changes_requested}</span>
                          : <span className="text-gray-300">—</span>}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        {r.commented > 0
                          ? <span className="text-blue-500">{r.commented}</span>
                          : <span className="text-gray-300">—</span>}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        {r.dismissed > 0
                          ? <span className="text-gray-400">{r.dismissed}</span>
                          : <span className="text-gray-300">—</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Status tabs */}
        <div className="flex gap-1 mb-4 border-b border-gray-200">
          {STATUSES.map((s) => (
            <Link
              key={s}
              href={tabHref(s)}
              className={`px-4 py-2 text-sm font-medium rounded-t-md transition-colors capitalize ${
                statusParam === s
                  ? "bg-white border border-b-white border-gray-200 text-blue-600 -mb-px"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {s}
            </Link>
          ))}
        </div>

        {/* Table */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-x-auto">
          {prs.length === 0 ? (
            <p className="py-12 text-center text-sm text-gray-400">No pull requests found.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Title</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Repository</th>
                  <th className="text-center px-4 py-3 font-medium text-gray-600">State</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Reviewers</th>
                  <th className="text-right px-4 py-3 font-medium text-gray-600">Opened</th>
                  <th className="text-right px-4 py-3 font-medium text-gray-600">Merged</th>
                  <th className="text-right px-4 py-3 font-medium text-gray-600 tabular-nums">+Lines</th>
                  <th className="text-right px-4 py-3 font-medium text-gray-600 tabular-nums">−Lines</th>
                  <th className="text-right px-4 py-3 font-medium text-gray-600">Files</th>
                  <th className="text-right px-4 py-3 font-medium text-gray-600">Commits</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {prs.map((pr) => (
                  <tr key={pr.id} className="hover:bg-blue-50 transition-colors">
                    <td className="px-4 py-3 max-w-xs">
                      <a
                        href={pr.github_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 hover:underline font-medium line-clamp-1"
                        title={pr.title}
                      >
                        #{pr.number} {pr.title}
                      </a>
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{pr.repo_full_name}</td>
                    <td className="px-4 py-3 text-center">
                      <StateBadge state={pr.state} />
                    </td>
                    <td className="px-4 py-3">
                      <ReviewerAvatars reviewers={pr.reviewers} />
                    </td>
                    <td className="px-4 py-3 text-right text-gray-600 text-xs tabular-nums whitespace-nowrap">
                      {fmtDate(pr.opened_at)}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-600 text-xs tabular-nums whitespace-nowrap">
                      {pr.merged_at ? fmtDate(pr.merged_at) : <span className="text-gray-300">—</span>}
                    </td>
                    <td className="px-4 py-3 text-right text-green-600 tabular-nums">
                      +{fmt(pr.additions)}
                    </td>
                    <td className="px-4 py-3 text-right text-red-500 tabular-nums">
                      −{fmt(pr.deletions)}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-600 tabular-nums">
                      {fmt(pr.changed_files)}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-600 tabular-nums">
                      {fmt(pr.commits_count)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <p className="mt-3 text-xs text-gray-400 text-right">{prs.length} pull request{prs.length !== 1 ? "s" : ""}</p>
      </div>
    </main>
  );
}
