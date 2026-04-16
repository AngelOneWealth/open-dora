"use client";

import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

// ─── Exported types (callers map their data to these shapes) ─────────────────

export type Series = {
  id: number;
  label: string;       // primary display text (repo short name, user name, etc.)
  sublabel?: string;   // secondary text (full repo path, @login, etc.)
  avatar_url?: string | null; // absent = no avatar column; null = initials; string = img
  href?: string;       // optional link on row click
};

export type WeeklyStat = {
  week_start: string;  // ISO date "YYYY-MM-DD"
  series_id: number;
  commits: number;
  net_lines: number;
};

export type StatRow = {
  series_id: number;
  commits: number;
  additions: number;
  deletions: number;
  prs_opened: number;
  prs_merged: number;
  reviews: number;
};

export type Totals = Omit<StatRow, "series_id">;

// ─── Internal types ───────────────────────────────────────────────────────────

type SortKey =
  | "label"
  | "commits"
  | "additions"
  | "deletions"
  | "net_lines"
  | "prs_opened"
  | "prs_merged"
  | "reviews";
type SortDir = "asc" | "desc";
type Metric = "net_lines" | "commits";

// ─── Constants ────────────────────────────────────────────────────────────────

const LINE_COLORS = [
  "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
  "#ec4899", "#06b6d4", "#f97316", "#84cc16", "#6366f1",
];

const STAT_COLS: { key: SortKey; label: string }[] = [
  { key: "commits",    label: "Commits"    },
  { key: "additions",  label: "Additions"  },
  { key: "deletions",  label: "Deletions"  },
  { key: "net_lines",  label: "Net Lines"  },
  { key: "prs_opened", label: "PRs Opened" },
  { key: "prs_merged", label: "PRs Merged" },
  { key: "reviews",    label: "Reviews"    },
];

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmt(n: number) { return n.toLocaleString("en-US"); }

function fmtK(v: number) {
  if (Math.abs(v) >= 1000) return `${(v / 1000).toFixed(1)}k`;
  return String(v);
}

function fmtWeekShort(iso: string) {
  const d = new Date(iso + "T00:00:00");
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function fmtWeekLong(iso: string) {
  const d = new Date(iso + "T00:00:00");
  const day = String(d.getDate()).padStart(2, "0");
  const month = d.toLocaleDateString("en-US", { month: "short" });
  return `Week of ${day} ${month}, ${d.getFullYear()}`;
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

// Avatar circle (only rendered when avatar_url is not undefined)
function Avatar({ s }: { s: Series }) {
  if (s.avatar_url === undefined) return null;
  return s.avatar_url ? (
    <img src={s.avatar_url} alt={s.label} className="w-7 h-7 rounded-full flex-shrink-0" />
  ) : (
    <div className="w-7 h-7 rounded-full bg-gray-200 flex items-center justify-center text-xs font-medium text-gray-500 flex-shrink-0">
      {s.label[0]?.toUpperCase()}
    </div>
  );
}

function LabelCell({ s }: { s: Series }) {
  return (
    <div>
      <div className="font-medium text-gray-900 group-hover:text-blue-600 group-hover:underline leading-snug">
        {s.label}
      </div>
      {s.sublabel && <div className="text-xs text-gray-400">{s.sublabel}</div>}
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function StatsPanel({
  series,
  weekly,
  rows,
  totals,
  startDate,
  endDate,
  basePath,
  chartTitle = "Weekly activity",
  firstColLabel = "Name",
  defaultSortKey = "commits",
  defaultSortDir = "desc",
}: {
  series: Series[];
  weekly: WeeklyStat[];
  rows: StatRow[];
  totals: Totals;
  startDate: string;
  endDate: string;
  /** URL base used for date-picker navigation, e.g. "/users/3", "/teams/1" */
  basePath: string;
  chartTitle?: string;
  firstColLabel?: string;
  defaultSortKey?: SortKey;
  defaultSortDir?: SortDir;
}) {
  const router = useRouter();
  const [sortKey, setSortKey] = useState<SortKey>(defaultSortKey);
  const [sortDir, setSortDir] = useState<SortDir>(defaultSortDir);
  const [metric, setMetric] = useState<Metric>("net_lines");

  function handleSort(key: SortKey) {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(key); setSortDir(key === "label" ? "asc" : "desc"); }
  }

  function handleDateChange(field: "start" | "end", value: string) {
    // Split basePath in case it already carries extra query params (e.g. ?ids=1,2,3)
    const [pathname, existingQuery] = basePath.split("?");
    const p = new URLSearchParams(existingQuery ?? "");
    p.set("start_date", field === "start" ? value : startDate);
    p.set("end_date",   field === "end"   ? value : endDate);
    router.push(`${pathname}?${p.toString()}`);
  }

  // Pivot flat weekly list → [{ week_start, s_<id>: value, …, total }]
  const chartData = useMemo(() => {
    const weeks = [...new Set(weekly.map((w) => w.week_start))].sort();
    return weeks.map((week) => {
      const entry: Record<string, string | number> = { week_start: week };
      let weekTotal = 0;
      for (const s of series) {
        const found = weekly.find((w) => w.week_start === week && w.series_id === s.id);
        const v = found ? found[metric] : 0;
        entry[`s_${s.id}`] = v;
        weekTotal += v;
      }
      entry["total"] = weekTotal;
      return entry;
    });
  }, [weekly, series, metric]);

  const sortedRows = useMemo(() => {
    return [...rows].sort((a, b) => {
      const sa = series.find((s) => s.id === a.series_id);
      const sb = series.find((s) => s.id === b.series_id);
      let av: number | string;
      let bv: number | string;
      if (sortKey === "label") {
        av = (sa?.label ?? "").toLowerCase();
        bv = (sb?.label ?? "").toLowerCase();
      } else if (sortKey === "net_lines") {
        av = a.additions - a.deletions;
        bv = b.additions - b.deletions;
      } else {
        av = a[sortKey];
        bv = b[sortKey];
      }
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [rows, series, sortKey, sortDir]);

  return (
    <div className="space-y-4">
      {/* Date pickers */}
      <div className="flex items-center gap-3 text-sm flex-wrap">
        <label className="text-gray-600 font-medium">From</label>
        <input
          type="date"
          defaultValue={startDate}
          onChange={(e) => handleDateChange("start", e.target.value)}
          className="px-2 py-1 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
        />
        <label className="text-gray-600 font-medium">To</label>
        <input
          type="date"
          defaultValue={endDate}
          onChange={(e) => handleDateChange("end", e.target.value)}
          className="px-2 py-1 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
        />
      </div>

      {/* Line chart */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
          <h2 className="text-base font-semibold text-gray-900">{chartTitle}</h2>
          <div className="flex gap-1 text-xs">
            {(["net_lines", "commits"] as Metric[]).map((m) => (
              <button
                key={m}
                onClick={() => setMetric(m)}
                className={`px-3 py-1.5 rounded-md border transition-colors ${
                  metric === m
                    ? "bg-blue-600 text-white border-blue-600"
                    : "bg-white text-gray-600 border-gray-300 hover:bg-gray-50"
                }`}
              >
                {m === "net_lines" ? "Net Lines" : "Commits"}
              </button>
            ))}
          </div>
        </div>

        {weekly.length === 0 ? (
          <p className="py-10 text-center text-sm text-gray-400">
            No commit activity in this date range.
          </p>
        ) : (
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={chartData} margin={{ top: 5, right: 16, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
              <XAxis
                dataKey="week_start"
                tick={{ fontSize: 11, fill: "#9ca3af" }}
                tickFormatter={fmtWeekShort}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                tick={{ fontSize: 11, fill: "#9ca3af" }}
                tickLine={false}
                axisLine={false}
                tickFormatter={fmtK}
              />
              <Tooltip
                labelFormatter={fmtWeekLong}
                formatter={(value: number, name: string) => {
                  if (name === "total") return [fmt(value), "Total"];
                  const id = parseInt(name.replace("s_", ""), 10);
                  const s = series.find((x) => x.id === id);
                  return [fmt(value), s?.label ?? name];
                }}
              />
              <Legend
                formatter={(value: string) => {
                  if (value === "total") return "Total";
                  const id = parseInt(value.replace("s_", ""), 10);
                  const s = series.find((x) => x.id === id);
                  return s?.label ?? value;
                }}
              />
              {metric === "net_lines" && (
                <ReferenceLine y={0} stroke="#e5e7eb" strokeWidth={1} />
              )}
              {series.map((s, i) => (
                <Line
                  key={s.id}
                  type="monotone"
                  dataKey={`s_${s.id}`}
                  stroke={LINE_COLORS[i % LINE_COLORS.length]}
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4 }}
                />
              ))}
              {series.length > 1 && (
                <Line
                  key="total"
                  type="monotone"
                  dataKey="total"
                  stroke="#111827"
                  strokeWidth={2}
                  strokeDasharray="5 3"
                  dot={false}
                  activeDot={{ r: 4 }}
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Stats table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-x-auto">
        {rows.length === 0 ? (
          <p className="px-4 py-10 text-center text-sm text-gray-400">
            No activity in this date range.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                {/* First column (sortable by label) */}
                <th className="text-left px-4 py-3 font-medium text-gray-600">
                  <button
                    onClick={() => handleSort("label")}
                    className="inline-flex items-center hover:text-gray-900"
                  >
                    {firstColLabel}
                    <SortIcon active={sortKey === "label"} dir={sortDir} />
                  </button>
                </th>
                {/* Stat columns */}
                {STAT_COLS.map((col) => (
                  <th
                    key={col.key}
                    className="text-right px-4 py-3 font-medium text-gray-600"
                  >
                    <button
                      onClick={() => handleSort(col.key)}
                      className="inline-flex items-center justify-end w-full hover:text-gray-900"
                    >
                      {col.label}
                      <SortIcon active={sortKey === col.key} dir={sortDir} />
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {sortedRows.map((row) => {
                const s = series.find((x) => x.id === row.series_id);
                const net = row.additions - row.deletions;
                const inner = s ? (
                  <>
                    <Avatar s={s} />
                    <LabelCell s={s} />
                  </>
                ) : null;

                return (
                  <tr key={row.series_id} className="hover:bg-blue-50 transition-colors">
                    <td className="px-4 py-3">
                      {s?.href ? (
                        <Link href={s.href} className="flex items-center gap-2 group">
                          {inner}
                        </Link>
                      ) : (
                        <div className="flex items-center gap-2">{inner}</div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-700">{fmt(row.commits)}</td>
                    <td className="px-4 py-3 text-right text-green-600">+{fmt(row.additions)}</td>
                    <td className="px-4 py-3 text-right text-red-500">-{fmt(row.deletions)}</td>
                    <td className={`px-4 py-3 text-right font-medium ${netColor(net)}`}>
                      {net >= 0 ? "+" : ""}{fmt(net)}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-700">{fmt(row.prs_opened)}</td>
                    <td className="px-4 py-3 text-right text-gray-700">{fmt(row.prs_merged)}</td>
                    <td className="px-4 py-3 text-right text-gray-700">{fmt(row.reviews)}</td>
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
        )}
      </div>
    </div>
  );
}
