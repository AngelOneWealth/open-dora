"use client";

import React, { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import SyncStatusPanel, { type RepoSyncState, type SyncSummary } from "@/app/components/SyncStatusPanel";

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

type SortKey = "name" | "contributors" | "commits" | "net_lines" | "prs_opened" | "reviews";
type SortDir = "asc" | "desc";

const PHASES = ["all", "commits", "prs", "reviews", "pr_commits"] as const;

function fmt(n: number) {
  return n.toLocaleString("en-US");
}

function netColor(n: number) {
  if (n > 0) return "text-green-600";
  if (n < 0) return "text-red-500";
  return "text-gray-400";
}

function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  return (
    <span className={`ml-1 text-xs ${active ? "text-blue-600" : "text-gray-300"}`}>
      {active && dir === "desc" ? "▼" : "▲"}
    </span>
  );
}

function fmtDate(d: Date) {
  // Use UTC methods so server (UTC) and browser produce identical HTML
  const day = String(d.getUTCDate()).padStart(2, "0");
  const month = d.toLocaleDateString("en-US", { month: "short", timeZone: "UTC" });
  return `${day} ${month}, ${d.getUTCFullYear()}`;
}

function SyncedAt({ ts }: { ts: string | null }) {
  if (!ts) return <span className="text-gray-300 text-xs">—</span>;
  const d = new Date(ts);
  const dateStr = fmtDate(d);
  const timeStr = d.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  });
  return (
    <span title={`${dateStr} ${timeStr} UTC`} className="text-gray-500 text-xs cursor-help tabular-nums">
      {dateStr}
    </span>
  );
}

export default function ReposList({ repos: initial }: { repos: Repo[] }) {
  const router = useRouter();
  const [repos, setRepos] = useState<Repo[]>(initial);
  const [sortKey, setSortKey] = useState<SortKey>("commits");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [syncing, setSyncing] = useState<Record<number, boolean>>({});
  const [syncPhase, setSyncPhase] = useState<Record<number, string>>({});
  const [syncRepos, setSyncRepos] = useState<Record<number, RepoSyncState[]>>({});
  const [syncSummary, setSyncSummary] = useState<Record<number, SyncSummary>>({});
  const [removing, setRemoving] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<Set<number>>(new Set());

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "name" ? "asc" : "desc");
    }
  }

  const sorted = useMemo(() => {
    return [...repos].sort((a, b) => {
      const av = sortKey === "name" ? a.name.toLowerCase() : a[sortKey];
      const bv = sortKey === "name" ? b.name.toLowerCase() : b[sortKey];
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [repos, sortKey, sortDir]);

  async function handleSync(repoId: number) {
    const phases = syncPhase[repoId] ?? "all";
    setSyncing((s) => ({ ...s, [repoId]: true }));
    setSyncRepos((s) => ({ ...s, [repoId]: [] }));
    setSyncSummary((s) => { const n = { ...s }; delete n[repoId]; return n; });

    try {
      // Step 1: fire-and-forget POST — returns immediately with job_id
      const postRes = await fetch(`/api/repos/${repoId}/sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phases }),
      });
      if (!postRes.ok) throw new Error("sync failed to start");
      const { job_id } = await postRes.json();

      // Step 2: connect to the NDJSON stream for this job
      const res = await fetch(`/api/repos/${repoId}/sync?job_id=${job_id}`);

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let lineBuffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        lineBuffer += decoder.decode(value, { stream: true });
        const lastNL = lineBuffer.lastIndexOf("\n");
        if (lastNL === -1) continue;
        const complete = lineBuffer.slice(0, lastNL + 1);
        lineBuffer = lineBuffer.slice(lastNL + 1);
        for (const line of complete.split("\n")) {
          if (!line.trim()) continue;
          try {
            const msg = JSON.parse(line);
            if (msg.type === "repo") {
              setSyncRepos((s) => ({ ...s, [repoId]: [msg as RepoSyncState] }));
            } else if (msg.type === "summary") {
              setSyncSummary((s) => ({ ...s, [repoId]: msg as SyncSummary }));
            }
          } catch { /* ignore non-JSON lines */ }
        }
      }
    } finally {
      setSyncing((s) => ({ ...s, [repoId]: false }));
      router.refresh();
    }
  }

  async function handleRemove(repoId: number) {
    setDeleting((s) => new Set(s).add(repoId));
    setRemoving(null);
    try {
      const res = await fetch(`/api/repos/${repoId}`, { method: "DELETE" });
      if (res.ok) {
        setRepos((prev) => prev.filter((r) => r.id !== repoId));
      }
    } finally {
      setDeleting((s) => { const n = new Set(s); n.delete(repoId); return n; });
    }
  }

  function th(label: React.ReactNode, key: SortKey, align: "left" | "right" = "right") {
    return (
      <th className={`text-${align} px-4 py-3 font-medium text-gray-600`}>
        <button
          onClick={() => handleSort(key)}
          className="hover:text-blue-600 transition-colors inline-flex items-center gap-0.5"
        >
          {label}
          <SortIcon active={sortKey === key} dir={sortDir} />
        </button>
      </th>
    );
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-x-auto">
      {sorted.length === 0 ? (
        <p className="px-4 py-6 text-sm text-gray-400 text-center">No repositories yet.</p>
      ) : (
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              {th("Repository", "name", "left")}
              {th(
                <><span>Contributors</span> <span className="text-gray-400 font-normal text-xs">(6m)</span></>,
                "contributors"
              )}
              {th(
                <><span>Commits</span> <span className="text-gray-400 font-normal text-xs">(6m)</span></>,
                "commits"
              )}
              {th(
                <><span>Net Lines</span> <span className="text-gray-400 font-normal text-xs">(6m)</span></>,
                "net_lines"
              )}
              {th(
                <><span>PRs</span> <span className="text-gray-400 font-normal text-xs">(6m)</span></>,
                "prs_opened"
              )}
              {th(
                <><span>Reviews</span> <span className="text-gray-400 font-normal text-xs">(6m)</span></>,
                "reviews"
              )}
              <th className="text-right px-4 py-3 font-medium text-gray-600 text-xs">Commits ↺</th>
              <th className="text-right px-4 py-3 font-medium text-gray-600 text-xs">PRs ↺</th>
              <th className="text-right px-4 py-3 font-medium text-gray-600 text-xs">Reviews ↺</th>
              <th className="text-right px-4 py-3 font-medium text-gray-600 text-xs">PR Commits ↺</th>
              <th className="text-right px-4 py-3 font-medium text-gray-600">Sync</th>
              <th className="text-right px-4 py-3 font-medium text-gray-600"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {sorted.map((repo) => (
              <React.Fragment key={repo.id}>
                <tr className="hover:bg-blue-50 transition-colors">
                  <td className="px-4 py-3">
                    <Link href={`/repos/${repo.id}`} className="font-medium text-blue-600 hover:underline">
                      {repo.name}
                    </Link>
                    <div className="text-xs text-gray-400">{repo.owner}</div>
                  </td>
                  <td className="px-4 py-3 text-right text-gray-700 tabular-nums">
                    {fmt(repo.contributors)}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-700 tabular-nums">
                    {fmt(repo.commits)}
                  </td>
                  <td className={`px-4 py-3 text-right tabular-nums font-medium ${netColor(repo.net_lines)}`}>
                    {repo.net_lines >= 0 ? "+" : ""}{fmt(repo.net_lines)}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-700 tabular-nums">
                    {fmt(repo.prs_opened)}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-700 tabular-nums">
                    {fmt(repo.reviews)}
                  </td>
                  <td className="px-4 py-3 text-right"><SyncedAt ts={repo.commits_synced_at} /></td>
                  <td className="px-4 py-3 text-right"><SyncedAt ts={repo.prs_synced_at} /></td>
                  <td className="px-4 py-3 text-right"><SyncedAt ts={repo.reviews_synced_at} /></td>
                  <td className="px-4 py-3 text-right"><SyncedAt ts={repo.pr_commits_synced_at} /></td>
                  <td className="px-4 py-3 text-right">
                    <div className="inline-flex rounded-md shadow-sm">
                      <button
                        onClick={() => handleSync(repo.id)}
                        disabled={syncing[repo.id]}
                        className="px-2 py-1 text-xs rounded-l-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 transition-colors"
                      >
                        {syncing[repo.id] ? "…" : "Sync"}
                      </button>
                      <select
                        value={syncPhase[repo.id] ?? "all"}
                        onChange={(e) => setSyncPhase((s) => ({ ...s, [repo.id]: e.target.value }))}
                        disabled={syncing[repo.id]}
                        className="px-1 py-1 text-xs rounded-r-md border-l border-blue-500 bg-blue-600 text-white cursor-pointer disabled:opacity-40"
                      >
                        {PHASES.map((p) => <option key={p} value={p}>{p}</option>)}
                      </select>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right">
                    {removing === repo.id ? (
                      <span className="flex items-center gap-1 text-xs justify-end">
                        <span className="text-red-600 font-medium">Remove?</span>
                        <button onClick={() => handleRemove(repo.id)} className="px-2 py-0.5 rounded bg-red-600 text-white hover:bg-red-700 text-xs">Yes</button>
                        <button onClick={() => setRemoving(null)} className="px-2 py-0.5 rounded border border-gray-300 text-gray-600 hover:bg-gray-50 text-xs">No</button>
                      </span>
                    ) : (
                      <button
                        onClick={() => setRemoving(repo.id)}
                        disabled={deleting.has(repo.id) || syncing[repo.id]}
                        className="px-2.5 py-1 text-xs rounded-md border border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-40 transition-colors"
                      >
                        {deleting.has(repo.id) ? "Removing…" : "Remove"}
                      </button>
                    )}
                  </td>
                </tr>
                {(syncRepos[repo.id]?.length > 0 || syncing[repo.id]) && (
                  <tr>
                    <td colSpan={13} className="px-4 pb-3">
                      <SyncStatusPanel
                        repos={syncRepos[repo.id] ?? []}
                        summary={syncSummary[repo.id] ?? null}
                        syncing={syncing[repo.id] ?? false}
                      />
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
