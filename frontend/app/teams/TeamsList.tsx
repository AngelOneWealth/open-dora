"use client";

import { useState, useMemo } from "react";
import Link from "next/link";

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

type SortKey = "name" | "member_count" | "commits" | "net_lines" | "prs_opened" | "reviews";
type SortDir = "asc" | "desc";

function fmt(n: number) {
  return n.toLocaleString("en-US");
}

function fmtDate(d: Date) {
  // Use UTC methods so server (UTC) and browser produce identical HTML
  const day = String(d.getUTCDate()).padStart(2, "0");
  const month = d.toLocaleDateString("en-US", { month: "short", timeZone: "UTC" });
  return `${day} ${month}, ${d.getUTCFullYear()}`;
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

export default function TeamsList({ teams: initial }: { teams: Team[] }) {
  const [teams, setTeams] = useState(initial);
  const [sortKey, setSortKey] = useState<SortKey>("commits");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "name" ? "asc" : "desc");
    }
  }

  const sorted = useMemo(() => {
    return [...teams].sort((a, b) => {
      const av = sortKey === "name" ? a.name.toLowerCase() : a[sortKey];
      const bv = sortKey === "name" ? b.name.toLowerCase() : b[sortKey];
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [teams, sortKey, sortDir]);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const res = await fetch("/api/teams", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim() }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(data?.detail ?? "Failed to create team");
      } else {
        const team = await res.json();
        setTeams((prev) => [...prev, team].sort((a, b) => a.name.localeCompare(b.name)));
        setName("");
      }
    } catch {
      setError("Failed to create team");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-x-auto">
        {teams.length === 0 ? (
          <p className="px-4 py-6 text-sm text-gray-400 text-center">No teams yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">
                  <button onClick={() => handleSort("name")} className="hover:text-blue-600 transition-colors inline-flex items-center gap-0.5">
                    Team <SortIcon active={sortKey === "name"} dir={sortDir} />
                  </button>
                </th>
                <th className="text-right px-4 py-3 font-medium text-gray-600">
                  <button onClick={() => handleSort("member_count")} className="hover:text-blue-600 transition-colors inline-flex items-center gap-0.5">
                    Members <SortIcon active={sortKey === "member_count"} dir={sortDir} />
                  </button>
                </th>
                <th className="text-right px-4 py-3 font-medium text-gray-600">
                  <button onClick={() => handleSort("commits")} className="hover:text-blue-600 transition-colors inline-flex items-center gap-0.5">
                    Commits <span className="text-gray-400 font-normal text-xs">(6m)</span>
                    <SortIcon active={sortKey === "commits"} dir={sortDir} />
                  </button>
                </th>
                <th className="text-right px-4 py-3 font-medium text-gray-600">
                  <button onClick={() => handleSort("net_lines")} className="hover:text-blue-600 transition-colors inline-flex items-center gap-0.5">
                    Net Lines <span className="text-gray-400 font-normal text-xs">(6m)</span>
                    <SortIcon active={sortKey === "net_lines"} dir={sortDir} />
                  </button>
                </th>
                <th className="text-right px-4 py-3 font-medium text-gray-600">
                  <button onClick={() => handleSort("prs_opened")} className="hover:text-blue-600 transition-colors inline-flex items-center gap-0.5">
                    PRs <span className="text-gray-400 font-normal text-xs">(6m)</span>
                    <SortIcon active={sortKey === "prs_opened"} dir={sortDir} />
                  </button>
                </th>
                <th className="text-right px-4 py-3 font-medium text-gray-600">
                  <button onClick={() => handleSort("reviews")} className="hover:text-blue-600 transition-colors inline-flex items-center gap-0.5">
                    Reviews <span className="text-gray-400 font-normal text-xs">(6m)</span>
                    <SortIcon active={sortKey === "reviews"} dir={sortDir} />
                  </button>
                </th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {sorted.map((team) => (
                <tr key={team.id} className="hover:bg-blue-50 transition-colors">
                  <td className="px-4 py-3 font-medium">
                    <Link href={`/teams/${team.id}`} className="text-blue-600 hover:underline">
                      {team.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-right text-gray-700 tabular-nums">
                    {fmt(team.member_count)}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-700 tabular-nums">
                    {fmt(team.commits)}
                  </td>
                  <td className={`px-4 py-3 text-right tabular-nums font-medium ${netColor(team.net_lines)}`}>
                    {team.net_lines >= 0 ? "+" : ""}{fmt(team.net_lines)}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-700 tabular-nums">
                    {fmt(team.prs_opened)}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-700 tabular-nums">
                    {fmt(team.reviews)}
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {fmtDate(new Date(team.created_at))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4">
        <h2 className="text-sm font-medium text-gray-700 mb-3">New Team</h2>
        <form onSubmit={handleCreate} className="flex gap-2">
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Team name"
            className="flex-1 text-sm px-3 py-1.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
          <button
            type="submit"
            disabled={creating || !name.trim()}
            className="px-3 py-1.5 text-sm rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {creating ? "Creating…" : "Create"}
          </button>
        </form>
        {error && <p className="mt-2 text-xs text-red-500">{error}</p>}
      </div>
    </div>
  );
}
