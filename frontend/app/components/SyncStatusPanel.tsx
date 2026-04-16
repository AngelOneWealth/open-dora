"use client";

// ── Types ──────────────────────────────────────────────────────────────────────

export type PhaseStatus = "pending" | "syncing" | "done" | "error" | "skipped";

export type RepoSyncState = {
  full_name: string;
  status: "pending" | "syncing" | "done" | "error";
  phase: string;
  commits: number;
  prs: number;
  reviews: number;
  users_enriched: number;
  commits_status: PhaseStatus;
  prs_status: PhaseStatus;
  reviews_status: PhaseStatus;
  pr_commits_status: PhaseStatus;
};

export type SyncSummary = {
  done: number;
  failed: number;
  total_commits: number;
  total_prs: number;
  total_reviews: number;
};

// ── PhaseBadge ─────────────────────────────────────────────────────────────────

function PhaseBadge({ status, label }: { status: PhaseStatus; label: string }) {
  if (status === "done") {
    return (
      <span title={label} className="inline-flex items-center gap-0.5 text-green-600 font-medium">
        <span>✓</span>
        <span className="text-xs">{label}</span>
      </span>
    );
  }
  if (status === "syncing") {
    return (
      <span title={label} className="inline-flex items-center gap-0.5 text-blue-600 font-medium">
        <span className="inline-block animate-spin">⟳</span>
        <span className="text-xs">{label}</span>
      </span>
    );
  }
  if (status === "error") {
    return (
      <span title={label} className="inline-flex items-center gap-0.5 text-red-600 font-medium">
        <span>✗</span>
        <span className="text-xs">{label}</span>
      </span>
    );
  }
  if (status === "skipped") {
    return (
      <span title={label} className="inline-flex items-center gap-0.5 text-gray-400">
        <span>—</span>
        <span className="text-xs">{label}</span>
      </span>
    );
  }
  // pending
  return (
    <span title={label} className="inline-flex items-center gap-0.5 text-gray-400">
      <span>·</span>
      <span className="text-xs">{label}</span>
    </span>
  );
}

// ── SyncStatusPanel ────────────────────────────────────────────────────────────

export default function SyncStatusPanel({
  repos,
  summary,
  syncing,
}: {
  repos: RepoSyncState[];
  summary: SyncSummary | null;
  syncing: boolean;
}) {
  const showSpinner = syncing && repos.length === 0;

  return (
    <div className="mt-1 rounded-md border border-gray-200 bg-gray-50 overflow-hidden">
      <table className="w-full text-xs">
        <tbody>
          {showSpinner && (
            <tr>
              <td className="px-3 py-2 text-gray-400 italic">
                <span className="inline-block animate-spin mr-1">⟳</span>
                Starting sync…
              </td>
            </tr>
          )}

          {repos.map((repo) => (
            <tr key={repo.full_name} className="border-b border-gray-100 last:border-0">
              {/* Repository name */}
              <td className="px-3 py-2 font-medium text-gray-700 whitespace-nowrap max-w-[160px] truncate" title={repo.full_name}>
                {repo.full_name.split("/").pop() ?? repo.full_name}
              </td>

              {/* Phase badges */}
              <td className="px-3 py-2">
                <div className="flex items-center gap-3">
                  <PhaseBadge status={repo.commits_status} label="commits" />
                  <PhaseBadge status={repo.prs_status} label="PRs" />
                  <PhaseBadge status={repo.reviews_status} label="reviews" />
                  <PhaseBadge status={repo.pr_commits_status} label="links" />
                </div>
              </td>

              {/* Counts */}
              <td className="px-3 py-2 tabular-nums text-gray-600 whitespace-nowrap">
                {repo.commits > 0 || repo.prs > 0 || repo.reviews > 0 ? (
                  <span>
                    {repo.commits > 0 && <span>{repo.commits.toLocaleString()}c</span>}
                    {repo.commits > 0 && repo.prs > 0 && <span className="text-gray-300 mx-1">·</span>}
                    {repo.prs > 0 && <span>{repo.prs.toLocaleString()}p</span>}
                    {repo.prs > 0 && repo.reviews > 0 && <span className="text-gray-300 mx-1">·</span>}
                    {repo.reviews > 0 && <span>{repo.reviews.toLocaleString()}r</span>}
                  </span>
                ) : (
                  <span className="text-gray-300">—</span>
                )}
              </td>

              {/* Current phase text */}
              <td className="px-3 py-2 text-gray-400 italic max-w-[240px] truncate">
                {repo.status === "error" ? (
                  <span className="text-red-500 not-italic">error</span>
                ) : repo.status === "syncing" && repo.phase ? (
                  repo.phase
                ) : repo.status === "done" ? (
                  <span className="text-green-600 not-italic">done</span>
                ) : null}
              </td>
            </tr>
          ))}

          {summary && (
            <tr className="bg-gray-100 border-t border-gray-200">
              <td colSpan={4} className="px-3 py-2 text-gray-600">
                <span className={summary.failed > 0 ? "text-red-600 font-medium" : "text-green-600 font-medium"}>
                  {summary.done} done{summary.failed > 0 ? ` · ${summary.failed} failed` : ""}
                </span>
                {(summary.total_commits > 0 || summary.total_prs > 0 || summary.total_reviews > 0) && (
                  <span className="text-gray-400 ml-2">
                    | {summary.total_commits.toLocaleString()} commits
                    {" · "}{summary.total_prs.toLocaleString()} PRs
                    {" · "}{summary.total_reviews.toLocaleString()} reviews
                  </span>
                )}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
