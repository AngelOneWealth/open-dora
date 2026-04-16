"use client";

import { useState } from "react";

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

type RowState = {
  selectedUserId: string;
  linking: boolean;
  error: string | null;
};

export default function MissingUsersList({
  authors: initial,
  total,
  users,
}: {
  authors: MissingAuthor[];
  total: number;
  users: User[];
}) {
  const [authors, setAuthors] = useState(initial);
  const [rows, setRows] = useState<Record<number, RowState>>({});

  function updateRow(i: number, patch: Partial<RowState>) {
    setRows((prev) => ({
      ...prev,
      [i]: { selectedUserId: "", linking: false, error: null, ...prev[i], ...patch },
    }));
  }

  async function handleLink(i: number, author: MissingAuthor) {
    const userId = parseInt(rows[i]?.selectedUserId ?? "");
    if (!userId) return;
    updateRow(i, { linking: true, error: null });
    try {
      const res = await fetch("/api/users/missing/link", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          author_name: author.author_name,
          author_email: author.author_email,
          user_id: userId,
        }),
      });
      if (!res.ok) throw new Error("Failed to link");
      setAuthors((prev) => prev.filter((_, idx) => idx !== i));
    } catch {
      updateRow(i, { linking: false, error: "Failed — try again" });
    }
  }

  if (authors.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-12 text-center text-gray-400">
        All git identities are linked. 🎉
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
      <div className="px-4 py-2 border-b border-gray-100 text-sm text-gray-500">
        {authors.length} of {total} remaining
      </div>
      <table className="w-full text-sm">
        <thead className="bg-gray-50 border-b border-gray-200">
          <tr>
            <th className="text-left px-4 py-3 font-medium text-gray-600">Name</th>
            <th className="text-left px-4 py-3 font-medium text-gray-600">Email</th>
            <th className="text-right px-4 py-3 font-medium text-gray-600">Commits</th>
            <th className="text-left px-4 py-3 font-medium text-gray-600">Link to user</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {authors.map((a, i) => {
            const row = rows[i] ?? { selectedUserId: "", linking: false, error: null };
            return (
              <tr key={i} className="hover:bg-gray-50 transition-colors">
                <td className="px-4 py-3 font-medium text-gray-900">{a.author_name ?? "—"}</td>
                <td className="px-4 py-3 text-gray-500">{a.author_email ?? "—"}</td>
                <td className="px-4 py-3 text-right text-gray-700 font-medium">
                  {a.commit_count.toLocaleString("en-US")}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <select
                      value={row.selectedUserId}
                      onChange={(e) => updateRow(i, { selectedUserId: e.target.value })}
                      disabled={row.linking}
                      className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500 max-w-[220px]"
                    >
                      <option value="">— select user —</option>
                      {users.map((u) => (
                        <option key={u.id} value={u.id}>
                          {u.full_name ?? u.name ?? u.login}{u.full_name || u.name ? ` (@${u.login})` : ""}
                        </option>
                      ))}
                    </select>
                    <button
                      onClick={() => handleLink(i, a)}
                      disabled={!row.selectedUserId || row.linking}
                      className="px-3 py-1.5 text-sm rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    >
                      {row.linking ? "Linking…" : "Link"}
                    </button>
                    {row.error && (
                      <span className="text-xs text-red-500">{row.error}</span>
                    )}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
