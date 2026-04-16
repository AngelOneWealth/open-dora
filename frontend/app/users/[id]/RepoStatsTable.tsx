"use client";

import { useState, useMemo } from "react";
import Link from "next/link";

type RepoStatRow = {
  repo_id: number;
  repo_name: string;
  commits: number;
  additions: number;
  deletions: number;
  prs_opened: number;
  prs_merged: number;
  reviews: number;
};

type SortKey =
  | "repo_name"
  | "commits"
  | "additions"
  | "deletions"
  | "net_lines"
  | "prs_opened"
  | "prs_merged"
  | "reviews";
type SortDir = "asc" | "desc";

function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  return (
    <span className={`ml-1 inline-block text-xs ${active ? "text-blue-600" : "text-gray-300"}`}>
      {active && dir === "desc" ? "▼" : "▲"}
    </span>
  );
}

const COLUMNS: { key: SortKey; label: string; align?: "right" }[] = [
  { key: "repo_name", label: "Repository" },
  { key: "commits", label: "Commits", align: "right" },
  { key: "additions", label: "Additions", align: "right" },
  { key: "deletions", label: "Deletions", align: "right" },
  { key: "net_lines", label: "Net Lines", align: "right" },
  { key: "prs_opened", label: "PRs Opened", align: "right" },
  { key: "prs_merged", label: "PRs Merged", align: "right" },
  { key: "reviews", label: "Reviews", align: "right" },
];

function fmt(n: number) {
  return n.toLocaleString("en-US");
}

function netColor(n: number) {
  if (n > 0) return "text-green-600";
  if (n < 0) return "text-red-500";
  return "text-gray-400";
}

function shortName(full: string) {
  return full.split("/").pop() ?? full;
}

export default function RepoStatsTable({ repos }: { repos: RepoStatRow[] }) {
  const [sortKey, setSortKey] = useState<SortKey>("commits");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "repo_name" ? "asc" : "desc");
    }
  }

  const sorted = useMemo(() => {
    return [...repos].sort((a, b) => {
      let av: number | string;
      let bv: number | string;
      if (sortKey === "net_lines") {
        av = a.additions - a.deletions;
        bv = b.additions - b.deletions;
      } else if (sortKey === "repo_name") {
        av = a.repo_name.toLowerCase();
        bv = b.repo_name.toLowerCase();
      } else {
        av = a[sortKey];
        bv = b[sortKey];
      }
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [repos, sortKey, sortDir]);

  const totals = {
    commits: repos.reduce((s, r) => s + r.commits, 0),
    additions: repos.reduce((s, r) => s + r.additions, 0),
    deletions: repos.reduce((s, r) => s + r.deletions, 0),
    prs_opened: repos.reduce((s, r) => s + r.prs_opened, 0),
    prs_merged: repos.reduce((s, r) => s + r.prs_merged, 0),
    reviews: repos.reduce((s, r) => s + r.reviews, 0),
  };

  if (repos.length === 0) return null;

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-x-auto">
      <div className="px-6 py-4 border-b border-gray-100">
        <h2 className="text-base font-semibold text-gray-900">Activity by repository</h2>
      </div>
      <table className="w-full text-sm">
        <thead className="bg-gray-50 border-b border-gray-200">
          <tr>
            {COLUMNS.map((col) => (
              <th
                key={col.key}
                className={`px-4 py-3 font-medium text-gray-600 ${
                  col.align === "right" ? "text-right" : "text-left"
                }`}
              >
                <button
                  onClick={() => handleSort(col.key)}
                  className="inline-flex items-center hover:text-gray-900"
                >
                  {col.label}
                  <SortIcon active={sortKey === col.key} dir={sortDir} />
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {sorted.map((repo) => {
            const net = repo.additions - repo.deletions;
            return (
              <tr key={repo.repo_id} className="hover:bg-blue-50 transition-colors">
                <td className="px-4 py-3">
                  <Link
                    href={`/repos/${repo.repo_id}`}
                    className="font-medium text-gray-900 hover:text-blue-600 hover:underline"
                  >
                    {shortName(repo.repo_name)}
                  </Link>
                  <div className="text-xs text-gray-400">{repo.repo_name}</div>
                </td>
                <td className="px-4 py-3 text-right text-gray-700">{fmt(repo.commits)}</td>
                <td className="px-4 py-3 text-right text-green-600">+{fmt(repo.additions)}</td>
                <td className="px-4 py-3 text-right text-red-500">-{fmt(repo.deletions)}</td>
                <td className={`px-4 py-3 text-right font-medium ${netColor(net)}`}>
                  {net >= 0 ? "+" : ""}{fmt(net)}
                </td>
                <td className="px-4 py-3 text-right text-gray-700">{fmt(repo.prs_opened)}</td>
                <td className="px-4 py-3 text-right text-gray-700">{fmt(repo.prs_merged)}</td>
                <td className="px-4 py-3 text-right text-gray-700">{fmt(repo.reviews)}</td>
              </tr>
            );
          })}

          {/* Totals row */}
          <tr className="bg-gray-50 border-t-2 border-gray-300 font-semibold">
            <td className="px-4 py-3 text-gray-700">Total</td>
            <td className="px-4 py-3 text-right text-gray-900">{fmt(totals.commits)}</td>
            <td className="px-4 py-3 text-right text-green-700">+{fmt(totals.additions)}</td>
            <td className="px-4 py-3 text-right text-red-600">-{fmt(totals.deletions)}</td>
            <td className={`px-4 py-3 text-right font-bold ${netColor(totals.additions - totals.deletions)}`}>
              {totals.additions - totals.deletions >= 0 ? "+" : ""}
              {fmt(totals.additions - totals.deletions)}
            </td>
            <td className="px-4 py-3 text-right text-gray-900">{fmt(totals.prs_opened)}</td>
            <td className="px-4 py-3 text-right text-gray-900">{fmt(totals.prs_merged)}</td>
            <td className="px-4 py-3 text-right text-gray-900">{fmt(totals.reviews)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
