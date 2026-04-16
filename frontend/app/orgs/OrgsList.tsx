"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import SyncStatusPanel, { type RepoSyncState, type SyncSummary } from "@/app/components/SyncStatusPanel";

type Org = {
  id: number;
  login: string;
  display_name: string | null;
  avatar_url: string | null;
  token_preview: string;
  repo_count: number;
  created_at: string;
};

function fmtDate(iso: string) {
  // Use UTC methods so server (UTC) and browser produce identical HTML
  const d = new Date(iso);
  const day   = String(d.getUTCDate()).padStart(2, "0");
  const month = d.toLocaleDateString("en-US", { month: "short", timeZone: "UTC" });
  return `${day} ${month}, ${d.getUTCFullYear()}`;
}

function OrgAvatar({ org }: { org: Org }) {
  if (org.avatar_url) {
    return <img src={org.avatar_url} alt={org.login} className="w-8 h-8 rounded-full flex-shrink-0" />;
  }
  return (
    <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center text-sm font-medium text-gray-600 flex-shrink-0">
      {org.login[0].toUpperCase()}
    </div>
  );
}

export default function OrgsList({ orgs: initial }: { orgs: Org[] }) {
  const router = useRouter();
  const [orgs, setOrgs]         = useState(initial);
  const [login, setLogin]       = useState("");
  const [token, setToken]       = useState("");
  const [creating, setCreating] = useState(false);
  const [createErr, setCreateErr] = useState<string | null>(null);

  // Per-row edit state
  const [editId, setEditId]       = useState<number | null>(null);
  const [editName, setEditName]   = useState("");
  const [editToken, setEditToken] = useState("");
  const [saving, setSaving]       = useState(false);
  const [saveErr, setSaveErr]     = useState<string | null>(null);

  // Delete confirmation
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Sync state
  const [syncing,     setSyncing]     = useState<Record<number, boolean>>({});
  const [syncPhase,   setSyncPhase]   = useState<Record<number, string>>({});
  const [syncRepos,   setSyncRepos]   = useState<Record<number, RepoSyncState[]>>({});
  const [syncSummary, setSyncSummary] = useState<Record<number, SyncSummary>>({});

  // Discover repos state
  const [discovering,    setDiscovering]    = useState<Record<number, boolean>>({});
  const [discoverResult, setDiscoverResult] = useState<Record<number, { added: number; total: number }>>({});

  // ── Create ────────────────────────────────────────────────────────────────

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!login.trim() || !token.trim()) return;
    setCreating(true);
    setCreateErr(null);
    try {
      const res = await fetch("/api/orgs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ login: login.trim(), github_token: token.trim() }),
      });
      const data = await res.json();
      if (!res.ok) {
        setCreateErr(data?.detail ?? "Failed to create organisation");
      } else {
        setOrgs((prev) => [...prev, data]);
        setLogin("");
        setToken("");
      }
    } catch {
      setCreateErr("Failed to create organisation");
    } finally {
      setCreating(false);
    }
  }

  // ── Edit ──────────────────────────────────────────────────────────────────

  function startEdit(org: Org) {
    setEditId(org.id);
    setEditName(org.display_name ?? "");
    setEditToken("");
    setSaveErr(null);
  }

  function cancelEdit() {
    setEditId(null);
    setSaveErr(null);
  }

  async function handleSave(org: Org) {
    setSaving(true);
    setSaveErr(null);
    const body: Record<string, string> = {};
    if (editName.trim() !== (org.display_name ?? "")) body.display_name = editName.trim();
    if (editToken.trim()) body.github_token = editToken.trim();
    try {
      const res = await fetch(`/api/orgs/${org.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) {
        setSaveErr(data?.detail ?? "Failed to save");
      } else {
        setOrgs((prev) => prev.map((o) => (o.id === org.id ? data : o)));
        setEditId(null);
      }
    } catch {
      setSaveErr("Failed to save");
    } finally {
      setSaving(false);
    }
  }

  // ── Delete ────────────────────────────────────────────────────────────────

  async function handleDelete(id: number) {
    setDeleting(true);
    try {
      await fetch(`/api/orgs/${id}`, { method: "DELETE" });
      setOrgs((prev) => prev.filter((o) => o.id !== id));
      setDeleteId(null);
    } catch {
      /* ignore */
    } finally {
      setDeleting(false);
    }
  }

  // ── Discover Repos ────────────────────────────────────────────────────────

  async function handleDiscover(orgId: number) {
    setDiscovering((s) => ({ ...s, [orgId]: true }));
    setDiscoverResult((s) => { const n = { ...s }; delete n[orgId]; return n; });
    try {
      const res = await fetch(`/api/orgs/${orgId}/repos`, { method: "POST" });
      const data = await res.json();
      if (res.ok) {
        setDiscoverResult((s) => ({ ...s, [orgId]: data }));
        // Update the repo_count in the local org list
        setOrgs((prev) =>
          prev.map((o) => o.id === orgId ? { ...o, repo_count: data.total } : o)
        );
      }
    } catch { /* ignore */ } finally {
      setDiscovering((s) => ({ ...s, [orgId]: false }));
    }
  }

  // ── Sync ──────────────────────────────────────────────────────────────────

  async function handleSync(orgId: number) {
    const phases = syncPhase[orgId] ?? "all";
    setSyncing((s) => ({ ...s, [orgId]: true }));
    setSyncRepos((s) => ({ ...s, [orgId]: [] }));
    setSyncSummary((s) => { const n = { ...s }; delete n[orgId]; return n; });
    try {
      // Step 1: fire-and-forget POST — returns immediately with job_id
      const postRes = await fetch(`/api/orgs/${orgId}/sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phases }),
      });
      if (!postRes.ok) throw new Error("sync failed to start");
      const { job_id } = await postRes.json();

      // Step 2: connect to the NDJSON stream for this job
      const res = await fetch(`/api/orgs/${orgId}/sync?job_id=${job_id}`);
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
              // Always replace — show only the currently-active repo
              setSyncRepos((s) => ({ ...s, [orgId]: [msg as RepoSyncState] }));
            } else if (msg.type === "summary") {
              setSyncSummary((s) => ({ ...s, [orgId]: msg as SyncSummary }));
            }
          } catch { /* ignore non-JSON lines */ }
        }
      }
    } finally {
      setSyncing((s) => ({ ...s, [orgId]: false }));
      router.refresh();
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-x-auto">
        {orgs.length === 0 ? (
          <p className="px-4 py-10 text-center text-sm text-gray-400">
            No organisations yet. Add one below.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Organisation</th>
                <th className="text-right px-4 py-3 font-medium text-gray-600">Repos</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Token</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Added</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {orgs.map((org) => {
                const isEditing = editId === org.id;
                return (
                  <React.Fragment key={org.id}>
                  <tr className="hover:bg-gray-50 transition-colors">
                    {/* Org identity */}
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <OrgAvatar org={org} />
                        <div>
                          {isEditing ? (
                            <input
                              type="text"
                              value={editName}
                              onChange={(e) => setEditName(e.target.value)}
                              placeholder="Display name"
                              className="text-sm px-2 py-1 border border-gray-300 rounded-md w-40 focus:outline-none focus:ring-2 focus:ring-blue-400"
                            />
                          ) : (
                            <div className="font-medium text-gray-900">
                              {org.display_name ?? org.login}
                            </div>
                          )}
                          <div className="text-xs text-gray-400">@{org.login}</div>
                        </div>
                      </div>
                    </td>

                    {/* Repo count */}
                    <td className="px-4 py-3 text-right text-gray-700 tabular-nums">
                      {org.repo_count}
                    </td>

                    {/* Token */}
                    <td className="px-4 py-3">
                      {isEditing ? (
                        <input
                          type="password"
                          value={editToken}
                          onChange={(e) => setEditToken(e.target.value)}
                          placeholder="New token (leave blank to keep)"
                          className="text-sm px-2 py-1 border border-gray-300 rounded-md w-56 focus:outline-none focus:ring-2 focus:ring-blue-400 font-mono"
                        />
                      ) : (
                        <code className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded font-mono">
                          {org.token_preview}
                        </code>
                      )}
                    </td>

                    {/* Added date */}
                    <td className="px-4 py-3 text-gray-500 text-xs whitespace-nowrap">
                      {fmtDate(org.created_at)}
                    </td>

                    {/* Actions */}
                    <td className="px-4 py-3 text-right">
                      {isEditing ? (
                        <div className="flex items-center justify-end gap-2">
                          {saveErr && <span className="text-xs text-red-500">{saveErr}</span>}
                          <button
                            onClick={() => handleSave(org)}
                            disabled={saving}
                            className="px-2.5 py-1 text-xs rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 transition-colors"
                          >
                            {saving ? "Saving…" : "Save"}
                          </button>
                          <button
                            onClick={cancelEdit}
                            disabled={saving}
                            className="px-2.5 py-1 text-xs rounded-md border border-gray-300 text-gray-600 hover:bg-gray-50 transition-colors"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : deleteId === org.id ? (
                        <div className="flex items-center justify-end gap-2">
                          <span className="text-xs text-gray-500">Remove?</span>
                          <button
                            onClick={() => handleDelete(org.id)}
                            disabled={deleting}
                            className="px-2.5 py-1 text-xs rounded-md bg-red-600 text-white hover:bg-red-700 disabled:opacity-40 transition-colors"
                          >
                            {deleting ? "Removing…" : "Yes"}
                          </button>
                          <button
                            onClick={() => setDeleteId(null)}
                            className="px-2.5 py-1 text-xs rounded-md border border-gray-300 text-gray-600 hover:bg-gray-50 transition-colors"
                          >
                            No
                          </button>
                        </div>
                      ) : (
                        <div className="flex items-center justify-end gap-2 flex-wrap">
                          {/* Discover Repos button */}
                          <div className="flex items-center gap-1.5">
                            <button
                              onClick={() => handleDiscover(org.id)}
                              disabled={discovering[org.id] || syncing[org.id]}
                              title="Fetch repos from GitHub and register them in the database"
                              className="px-2.5 py-1 text-xs rounded-md border border-violet-300 text-violet-700 bg-white hover:bg-violet-50 disabled:opacity-40 transition-colors"
                            >
                              {discovering[org.id] ? "Discovering…" : "Discover Repos"}
                            </button>
                            {discoverResult[org.id] && (
                              <span className="text-xs text-gray-500 tabular-nums whitespace-nowrap">
                                {discoverResult[org.id].total} repos
                                {discoverResult[org.id].added > 0 && (
                                  <span className="ml-1 text-green-600 font-medium">
                                    (+{discoverResult[org.id].added} new)
                                  </span>
                                )}
                              </span>
                            )}
                          </div>
                          {/* Sync split-button */}
                          <div className="inline-flex rounded-md shadow-sm">
                            <button
                              onClick={() => handleSync(org.id)}
                              disabled={syncing[org.id]}
                              className="px-2.5 py-1 text-xs rounded-l-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
                            >
                              {syncing[org.id] ? "Syncing…" : "Sync"}
                            </button>
                            <select
                              value={syncPhase[org.id] ?? "all"}
                              onChange={(e) => setSyncPhase((s) => ({ ...s, [org.id]: e.target.value }))}
                              disabled={syncing[org.id]}
                              className="text-xs px-1 py-1 border-l border-blue-700 rounded-r-md bg-blue-600 text-white disabled:opacity-50 focus:outline-none cursor-pointer"
                            >
                              {["all", "commits", "prs", "reviews", "pr_commits"].map((p) => (
                                <option key={p} value={p}>{p}</option>
                              ))}
                            </select>
                          </div>
                          <button
                            onClick={() => startEdit(org)}
                            title="Edit"
                            className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-md transition-colors"
                          >
                            ✏️
                          </button>
                          <button
                            onClick={() => setDeleteId(org.id)}
                            title="Remove"
                            className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-md transition-colors"
                          >
                            🗑️
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>

                  {/* Sync status panel — visible while syncing or after */}
                  {(syncRepos[org.id]?.length > 0 || syncing[org.id]) && (
                    <tr>
                      <td colSpan={5} className="px-4 pb-3">
                        <SyncStatusPanel
                          repos={syncRepos[org.id] ?? []}
                          summary={syncSummary[org.id] ?? null}
                          syncing={syncing[org.id] ?? false}
                        />
                      </td>
                    </tr>
                  )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Add org form */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">Add Organisation</h2>
        <form onSubmit={handleCreate} className="space-y-3">
          <div className="flex gap-3 flex-wrap">
            <div className="flex-1 min-w-40">
              <label className="block text-xs font-medium text-gray-600 mb-1">
                GitHub login
              </label>
              <input
                type="text"
                value={login}
                onChange={(e) => setLogin(e.target.value)}
                placeholder="my-org or username"
                className="w-full text-sm px-3 py-1.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>
            <div className="flex-1 min-w-56">
              <label className="block text-xs font-medium text-gray-600 mb-1">
                GitHub token (PAT)
              </label>
              <input
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="ghp_xxxxxxxxxxxx"
                className="w-full text-sm px-3 py-1.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono"
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={creating || !login.trim() || !token.trim()}
              className="px-4 py-1.5 text-sm rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors font-medium"
            >
              {creating ? "Adding…" : "Add Organisation"}
            </button>
            {createErr && <p className="text-xs text-red-500">{createErr}</p>}
          </div>
        </form>
        <p className="mt-3 text-xs text-gray-400">
          The token is stored and used for syncing repos in this org. It is never shown in full after saving.
        </p>
      </div>
    </div>
  );
}
