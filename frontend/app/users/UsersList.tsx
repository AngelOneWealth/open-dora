"use client";

import { useState, useMemo, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

type User = {
  id: number;
  login: string;
  name: string | null;
  full_name: string | null;
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

type SortKey = "name" | "commits" | "net_lines" | "prs_opened" | "reviews";
type SortDir = "asc" | "desc";

function SortIcon({ active, dir }: { active: boolean; dir: SortDir }) {
  return (
    <span className={`ml-1 inline-block text-xs ${active ? "text-blue-600" : "text-gray-300"}`}>
      {active && dir === "desc" ? "▼" : "▲"}
    </span>
  );
}

function fmt(n: number) {
  return n.toLocaleString("en-US");
}

function netColor(n: number) {
  if (n > 0) return "text-green-600";
  if (n < 0) return "text-red-500";
  return "text-gray-400";
}

function UserTable({
  users,
  teams,
  onToggleActive,
  onTeamChange,
  onRenameUser,
  toggling,
  assigning,
  renaming,
  errors,
  isActiveTab,
  selectedIds,
  onToggleSelect,
}: {
  users: User[];
  teams: Team[];
  onToggleActive: (id: number) => void;
  onTeamChange: (id: number, teamId: string) => void;
  onRenameUser: (id: number, name: string) => Promise<void>;
  toggling: Set<number>;
  assigning: Set<number>;
  renaming: Set<number>;
  errors: Record<number, string>;
  isActiveTab: boolean;
  selectedIds: Set<number>;
  onToggleSelect: (id: number) => void;
}) {
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingName, setEditingName] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);

  function startEdit(user: User) {
    setEditingId(user.id);
    setEditingName(user.full_name ?? "");
    setTimeout(() => inputRef.current?.select(), 0);
  }

  async function commitEdit(id: number) {
    await onRenameUser(id, editingName);
    setEditingId(null);
  }

  function cancelEdit() {
    setEditingId(null);
  }
  const [sortKey, setSortKey] = useState<SortKey>(isActiveTab ? "commits" : "name");
  const [sortDir, setSortDir] = useState<SortDir>(isActiveTab ? "desc" : "asc");

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "name" ? "asc" : "desc");
    }
  }

  const sorted = useMemo(() => {
    return [...users].sort((a, b) => {
      let av: string | number;
      let bv: string | number;
      if (sortKey === "name") {
        av = (a.full_name ?? a.name ?? a.login).toLowerCase();
        bv = (b.full_name ?? b.name ?? b.login).toLowerCase();
      } else {
        av = a[sortKey];
        bv = b[sortKey];
      }
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [users, sortKey, sortDir]);

  if (users.length === 0) {
    return (
      <p className="py-12 text-center text-sm text-gray-400">
        No {isActiveTab ? "active" : "inactive"} users.
      </p>
    );
  }

  return (
    <table className="w-full text-sm">
      <thead className="bg-gray-50 border-b border-gray-200">
        <tr>
          {/* Checkbox column — active tab only */}
          {isActiveTab && (
            <th className="w-10 px-3 py-3">
              <span className="sr-only">Select</span>
            </th>
          )}
          {/* User column — always shown */}
          <th className="text-left px-4 py-3 font-medium text-gray-600">
            <button onClick={() => handleSort("name")} className="flex items-center hover:text-gray-900">
              User <SortIcon active={sortKey === "name"} dir={sortDir} />
            </button>
          </th>

          {isActiveTab ? (
            <>
              {/* Active tab: commits + net lines + team */}
              <th className="text-right px-4 py-3 font-medium text-gray-600">
                <button
                  onClick={() => handleSort("commits")}
                  className="inline-flex items-center justify-end w-full hover:text-gray-900"
                >
                  Commits <span className="ml-1 text-gray-400 font-normal text-xs">(6m)</span>
                  <SortIcon active={sortKey === "commits"} dir={sortDir} />
                </button>
              </th>
              <th className="text-right px-4 py-3 font-medium text-gray-600">
                <button
                  onClick={() => handleSort("net_lines")}
                  className="inline-flex items-center justify-end w-full hover:text-gray-900"
                >
                  Net Lines <span className="ml-1 text-gray-400 font-normal text-xs">(6m)</span>
                  <SortIcon active={sortKey === "net_lines"} dir={sortDir} />
                </button>
              </th>
              <th className="text-right px-4 py-3 font-medium text-gray-600">
                <button
                  onClick={() => handleSort("prs_opened")}
                  className="inline-flex items-center justify-end w-full hover:text-gray-900"
                >
                  PRs <span className="ml-1 text-gray-400 font-normal text-xs">(6m)</span>
                  <SortIcon active={sortKey === "prs_opened"} dir={sortDir} />
                </button>
              </th>
              <th className="text-right px-4 py-3 font-medium text-gray-600">
                <button
                  onClick={() => handleSort("reviews")}
                  className="inline-flex items-center justify-end w-full hover:text-gray-900"
                >
                  Reviews <span className="ml-1 text-gray-400 font-normal text-xs">(6m)</span>
                  <SortIcon active={sortKey === "reviews"} dir={sortDir} />
                </button>
              </th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Team</th>
            </>
          ) : (
            <>
              {/* Inactive tab: login + email */}
              <th className="text-left px-4 py-3 font-medium text-gray-600">Login</th>
              <th className="text-left px-4 py-3 font-medium text-gray-600">Email</th>
            </>
          )}

          <th className="px-4 py-3" />
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-100">
        {sorted.map((user) => {
          const busy = toggling.has(user.id);
          const saving = assigning.has(user.id);
          return (
            <tr key={user.id} className={`hover:bg-blue-50 transition-colors ${selectedIds.has(user.id) ? "bg-blue-50" : ""}`}>
              {/* Checkbox cell — active tab only */}
              {isActiveTab && (
                <td className="px-3 py-3">
                  <input
                    type="checkbox"
                    checked={selectedIds.has(user.id)}
                    onChange={() => onToggleSelect(user.id)}
                    className="w-4 h-4 rounded border-gray-300 text-blue-600 cursor-pointer focus:ring-blue-500"
                  />
                </td>
              )}
              {/* User cell */}
              <td className="px-4 py-3">
                <div className="flex items-center gap-3">
                  <Link href={`/users/${user.id}`} className="flex-shrink-0">
                    {user.avatar_url ? (
                      <img src={user.avatar_url} alt={user.login} className="w-8 h-8 rounded-full" />
                    ) : (
                      <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center text-gray-500 font-medium text-xs">
                        {user.login[0].toUpperCase()}
                      </div>
                    )}
                  </Link>
                  {editingId === user.id ? (
                    <div className="flex items-center gap-1.5 min-w-0">
                      <input
                        ref={inputRef}
                        type="text"
                        value={editingName}
                        onChange={(e) => setEditingName(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") { e.preventDefault(); commitEdit(user.id); }
                          if (e.key === "Escape") cancelEdit();
                        }}
                        className="text-sm px-2 py-0.5 border border-blue-400 rounded focus:outline-none focus:ring-2 focus:ring-blue-400 w-36"
                        disabled={renaming.has(user.id)}
                      />
                      <button
                        onClick={() => commitEdit(user.id)}
                        disabled={renaming.has(user.id)}
                        className="text-xs px-2 py-0.5 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
                      >
                        {renaming.has(user.id) ? "…" : "Save"}
                      </button>
                      <button
                        onClick={cancelEdit}
                        disabled={renaming.has(user.id)}
                        className="text-xs px-2 py-0.5 rounded border border-gray-300 text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                      >
                        ✕
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-1.5 min-w-0 group/name">
                      <Link
                        href={`/users/${user.id}`}
                        className="font-medium text-gray-900 hover:text-blue-600 hover:underline truncate"
                      >
                        {user.full_name ?? user.name ?? user.login}
                      </Link>
                      <button
                        onClick={() => startEdit(user)}
                        title="Edit name"
                        className="opacity-0 group-hover/name:opacity-100 transition-opacity text-gray-400 hover:text-gray-600 text-xs leading-none p-0.5"
                      >
                        ✎
                      </button>
                    </div>
                  )}
                </div>
              </td>

              {isActiveTab ? (
                <>
                  {/* Commits */}
                  <td className="px-4 py-3 text-right text-gray-700 tabular-nums">
                    {fmt(user.commits)}
                  </td>
                  {/* Net lines */}
                  <td className={`px-4 py-3 text-right tabular-nums font-medium ${netColor(user.net_lines)}`}>
                    {user.net_lines >= 0 ? "+" : ""}{fmt(user.net_lines)}
                  </td>
                  {/* PRs opened */}
                  <td className="px-4 py-3 text-right text-gray-700 tabular-nums">
                    {fmt(user.prs_opened)}
                  </td>
                  {/* Reviews */}
                  <td className="px-4 py-3 text-right text-gray-700 tabular-nums">
                    {fmt(user.reviews)}
                  </td>
                  {/* Team dropdown */}
                  <td className="px-4 py-3">
                    <select
                      value={user.team_id ?? ""}
                      onChange={(e) => onTeamChange(user.id, e.target.value)}
                      disabled={saving}
                      className="text-xs px-2 py-1 border border-gray-200 rounded-md text-gray-700 bg-white disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-blue-400"
                    >
                      <option value="">— No team —</option>
                      {teams.map((t) => (
                        <option key={t.id} value={t.id}>{t.name}</option>
                      ))}
                    </select>
                  </td>
                </>
              ) : (
                <>
                  <td className="px-4 py-3 text-gray-500">@{user.login}</td>
                  <td className="px-4 py-3 text-gray-500">{user.email ?? "—"}</td>
                </>
              )}

              {/* Action button */}
              <td className="px-4 py-3 text-right">
                <div className="flex items-center justify-end gap-2">
                  {errors[user.id] && (
                    <span className="text-xs text-red-500">{errors[user.id]}</span>
                  )}
                  <button
                    onClick={() => onToggleActive(user.id)}
                    disabled={busy}
                    className={`px-2.5 py-1 text-xs rounded-md border transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                      isActiveTab
                        ? "border-red-200 text-red-600 hover:bg-red-50"
                        : "border-green-200 text-green-700 hover:bg-green-50"
                    }`}
                  >
                    {busy
                      ? isActiveTab ? "Deactivating…" : "Activating…"
                      : isActiveTab ? "Deactivate" : "Activate"}
                  </button>
                </div>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export default function UsersList({
  activeUsers: initialActive,
  inactiveUsers: initialInactive,
  teams,
}: {
  activeUsers: User[];
  inactiveUsers: User[];
  teams: Team[];
}) {
  const router = useRouter();
  const [activeUsers, setActiveUsers] = useState(initialActive);
  const [inactiveUsers, setInactiveUsers] = useState(initialInactive);
  const [tab, setTab] = useState<"active" | "inactive">("active");
  const [toggling, setToggling] = useState<Set<number>>(new Set());
  const [assigning, setAssigning] = useState<Set<number>>(new Set());
  const [renaming, setRenaming] = useState<Set<number>>(new Set());
  const [errors, setErrors] = useState<Record<number, string>>({});
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [showMergeModal, setShowMergeModal] = useState(false);
  const [merging, setMerging] = useState(false);
  const [mergeError, setMergeError] = useState<string | null>(null);
  const [mergePrimaryId, setMergePrimaryId] = useState<number | null>(null);

  function handleToggleSelect(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleMerge() {
    if (selectedIds.size !== 2 || mergePrimaryId === null) return;
    const [a, b] = [...selectedIds];
    const sourceId = mergePrimaryId === a ? b : a;
    setMerging(true);
    setMergeError(null);
    try {
      const res = await fetch(`/api/users/${mergePrimaryId}/merge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_id: sourceId }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setMergeError(data?.detail ?? "Merge failed");
        return;
      }
      // Remove source from active list
      setActiveUsers((prev) => prev.filter((u) => u.id !== sourceId));
      setSelectedIds(new Set());
      setShowMergeModal(false);
      setMergePrimaryId(null);
      router.refresh();
    } catch {
      setMergeError("Merge failed");
    } finally {
      setMerging(false);
    }
  }

  function openMergeModal() {
    const [first] = [...selectedIds];
    setMergePrimaryId(first); // default primary = first selected
    setMergeError(null);
    setShowMergeModal(true);
  }

  function handleCompare() {
    const end = new Date();
    const start = new Date(Date.now() - 180 * 24 * 60 * 60 * 1000);
    const fmt = (d: Date) => d.toISOString().slice(0, 10);
    const ids = [...selectedIds].join(",");
    router.push(`/users/compare?ids=${ids}&start_date=${fmt(start)}&end_date=${fmt(end)}`);
  }

  async function handleRenameUser(id: number, name: string) {
    setRenaming((prev) => new Set(prev).add(id));
    setErrors((prev) => { const e = { ...prev }; delete e[id]; return e; });
    try {
      const res = await fetch(`/api/users/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ full_name: name.trim() }),
      });
      if (!res.ok) throw new Error();
      const updated: User = await res.json();
      setActiveUsers((prev) => prev.map((u) => u.id === id ? { ...u, full_name: updated.full_name } : u));
      setInactiveUsers((prev) => prev.map((u) => u.id === id ? { ...u, full_name: updated.full_name } : u));
    } catch {
      setErrors((prev) => ({ ...prev, [id]: "Failed to rename" }));
    } finally {
      setRenaming((prev) => { const s = new Set(prev); s.delete(id); return s; });
    }
  }

  async function handleToggleActive(id: number, currentlyActive: boolean) {
    setToggling((prev) => new Set(prev).add(id));
    setErrors((prev) => { const e = { ...prev }; delete e[id]; return e; });
    try {
      const res = await fetch(`/api/users/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active: !currentlyActive }),
      });
      if (!res.ok) throw new Error();
      const updated: User = await res.json();
      if (currentlyActive) {
        setActiveUsers((prev) => prev.filter((u) => u.id !== id));
        setInactiveUsers((prev) => [...prev, { ...updated, active: false }]);
      } else {
        setInactiveUsers((prev) => prev.filter((u) => u.id !== id));
        setActiveUsers((prev) => [...prev, { ...updated, active: true }]);
      }
    } catch {
      setErrors((prev) => ({ ...prev, [id]: "Failed" }));
    } finally {
      setToggling((prev) => { const s = new Set(prev); s.delete(id); return s; });
    }
  }

  async function handleTeamChange(id: number, teamId: string) {
    setAssigning((prev) => new Set(prev).add(id));
    setErrors((prev) => { const e = { ...prev }; delete e[id]; return e; });
    const parsed = parseInt(teamId, 10);
    const newTeamId = isNaN(parsed) ? null : parsed;
    const newTeamName = teams.find((t) => t.id === newTeamId)?.name ?? null;
    setActiveUsers((prev) =>
      prev.map((u) => u.id === id ? { ...u, team_id: newTeamId, team_name: newTeamName } : u)
    );
    try {
      const res = await fetch(`/api/users/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ team_id: isNaN(parsed) ? -1 : parsed }),
      });
      if (!res.ok) throw new Error();
    } catch {
      setErrors((prev) => ({ ...prev, [id]: "Failed to save team" }));
      setActiveUsers((prev) =>
        prev.map((u) =>
          u.id === id
            ? {
                ...u,
                team_id: initialActive.find((x) => x.id === id)?.team_id ?? null,
                team_name: initialActive.find((x) => x.id === id)?.team_name ?? null,
              }
            : u
        )
      );
    } finally {
      setAssigning((prev) => { const s = new Set(prev); s.delete(id); return s; });
    }
  }

  return (
    <div>
      {/* Tabs + Compare bar */}
      <div className="flex items-center gap-1 mb-4 border-b border-gray-200">
        {(["active", "inactive"] as const).map((t) => (
          <button
            key={t}
            onClick={() => { setTab(t); setSelectedIds(new Set()); }}
            className={`px-4 py-2 text-sm font-medium rounded-t-md transition-colors ${
              tab === t
                ? "bg-white border border-b-white border-gray-200 text-blue-600 -mb-px"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
            <span className="ml-2 text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded-full">
              {t === "active" ? activeUsers.length : inactiveUsers.length}
            </span>
          </button>
        ))}

        {/* Compare bar — appears when ≥2 active users are checked */}
        {selectedIds.size >= 1 && (
          <div className="ml-auto flex items-center gap-3 pb-1">
            <span className="text-sm text-gray-500">
              {selectedIds.size} selected
            </span>
            {selectedIds.size >= 2 && (
              <button
                onClick={handleCompare}
                className="px-3 py-1.5 text-sm rounded-md bg-blue-600 text-white hover:bg-blue-700 transition-colors font-medium"
              >
                Compare ({selectedIds.size})
              </button>
            )}
            {selectedIds.size === 2 && tab === "active" && (
              <button
                onClick={openMergeModal}
                className="px-3 py-1.5 text-sm rounded-md bg-orange-500 text-white hover:bg-orange-600 transition-colors font-medium"
              >
                Merge
              </button>
            )}
            <button
              onClick={() => setSelectedIds(new Set())}
              className="px-3 py-1.5 text-sm rounded-md border border-gray-300 text-gray-600 hover:bg-gray-50 transition-colors"
            >
              Clear
            </button>
          </div>
        )}
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        {tab === "active" ? (
          <UserTable
            users={activeUsers}
            teams={teams}
            onToggleActive={(id) => handleToggleActive(id, true)}
            onTeamChange={handleTeamChange}
            onRenameUser={handleRenameUser}
            toggling={toggling}
            assigning={assigning}
            renaming={renaming}
            errors={errors}
            isActiveTab={true}
            selectedIds={selectedIds}
            onToggleSelect={handleToggleSelect}
          />
        ) : (
          <UserTable
            users={inactiveUsers}
            teams={teams}
            onToggleActive={(id) => handleToggleActive(id, false)}
            onTeamChange={handleTeamChange}
            onRenameUser={handleRenameUser}
            toggling={toggling}
            assigning={assigning}
            renaming={renaming}
            errors={errors}
            isActiveTab={false}
            selectedIds={selectedIds}
            onToggleSelect={handleToggleSelect}
          />
        )}
      </div>

      {showMergeModal && selectedIds.size === 2 && (() => {
        const [idA, idB] = [...selectedIds];
        const userA = activeUsers.find((u) => u.id === idA)!;
        const userB = activeUsers.find((u) => u.id === idB)!;
        const users = [userA, userB];
        return (
          <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-1">Merge Duplicate Users</h2>
              <p className="text-sm text-gray-500 mb-5">
                Select which user to <span className="font-medium text-green-600">keep</span>. All commits, PRs and reviews from the other will be reassigned to them, then the duplicate will be deactivated.
              </p>

              <div className="grid grid-cols-2 gap-3 mb-5">
                {users.map((u) => {
                  const isPrimary = mergePrimaryId === u.id;
                  return (
                    <button
                      key={u.id}
                      onClick={() => setMergePrimaryId(u.id)}
                      className={`flex flex-col items-center gap-2 p-4 rounded-xl border-2 transition-colors text-center ${
                        isPrimary
                          ? "border-green-500 bg-green-50"
                          : "border-red-200 bg-red-50"
                      }`}
                    >
                      {u.avatar_url ? (
                        <img src={u.avatar_url} alt={u.login} className="w-12 h-12 rounded-full" />
                      ) : (
                        <div className="w-12 h-12 rounded-full bg-gray-200 flex items-center justify-center text-gray-500 font-bold text-lg">
                          {(u.full_name ?? u.name ?? u.login)[0].toUpperCase()}
                        </div>
                      )}
                      <div>
                        <div className="font-medium text-gray-900 text-sm">{u.full_name ?? u.name ?? u.login}</div>
                        <div className="text-xs text-gray-400">@{u.login}</div>
                      </div>
                      <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                        isPrimary ? "bg-green-100 text-green-700" : "bg-red-100 text-red-600"
                      }`}>
                        {isPrimary ? "✓ Keep" : "✕ Remove"}
                      </span>
                    </button>
                  );
                })}
              </div>

              {mergeError && (
                <p className="text-sm text-red-500 mb-3">{mergeError}</p>
              )}

              <div className="flex gap-2 justify-end">
                <button
                  onClick={() => { setShowMergeModal(false); setMergeError(null); }}
                  disabled={merging}
                  className="px-4 py-2 text-sm rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  onClick={handleMerge}
                  disabled={merging}
                  className="px-4 py-2 text-sm rounded-lg bg-orange-500 text-white hover:bg-orange-600 disabled:opacity-50 font-medium"
                >
                  {merging ? "Merging…" : "Merge"}
                </button>
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}
