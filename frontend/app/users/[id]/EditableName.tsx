"use client";

import { useState, useRef } from "react";

export default function EditableName({
  userId,
  fullName,
  fallback,
}: {
  userId: number;
  fullName: string | null;
  fallback: string;         // name ?? login
}) {
  const [editing, setEditing]   = useState(false);
  const [value,   setValue]     = useState(fullName ?? "");
  const [saving,  setSaving]    = useState(false);
  const [current, setCurrent]   = useState(fullName); // optimistic display
  const inputRef = useRef<HTMLInputElement>(null);

  function startEdit() {
    setValue(current ?? "");
    setEditing(true);
    setTimeout(() => { inputRef.current?.select(); }, 0);
  }

  async function commit() {
    setSaving(true);
    try {
      const res = await fetch(`/api/users/${userId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ full_name: value.trim() }),
      });
      if (res.ok) {
        const updated = await res.json();
        setCurrent(updated.full_name ?? null);
      }
    } finally {
      setSaving(false);
      setEditing(false);
    }
  }

  function cancel() {
    setEditing(false);
  }

  const displayName = current ?? fallback;

  if (editing) {
    return (
      <div className="flex items-center gap-2 flex-wrap">
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") { e.preventDefault(); commit(); }
            if (e.key === "Escape") cancel();
          }}
          placeholder={fallback}
          disabled={saving}
          className="text-2xl font-bold text-gray-900 px-2 py-0.5 border border-blue-400 rounded focus:outline-none focus:ring-2 focus:ring-blue-400 w-72 disabled:opacity-60"
        />
        <button
          onClick={commit}
          disabled={saving}
          className="px-3 py-1 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save"}
        </button>
        <button
          onClick={cancel}
          disabled={saving}
          className="px-3 py-1 text-sm rounded border border-gray-300 text-gray-600 hover:bg-gray-50 disabled:opacity-50"
        >
          Cancel
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 group/name">
      <h1 className="text-3xl font-bold text-gray-900">{displayName}</h1>
      <button
        onClick={startEdit}
        title="Edit name"
        className="opacity-0 group-hover/name:opacity-100 transition-opacity text-gray-400 hover:text-gray-600 text-sm leading-none p-1"
      >
        ✎
      </button>
    </div>
  );
}
