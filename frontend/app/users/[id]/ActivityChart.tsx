"use client";

import { useState, useMemo } from "react";
import { useRouter } from "next/navigation";
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

type RepoStatRow = {
  repo_id: number;
  repo_name: string;
};

type WeeklyRepoStat = {
  week_start: string;
  repo_id: number;
  commits: number;
  net_lines: number;
};

type Props = {
  userId: string;
  repos: RepoStatRow[];
  weeklyByRepo: WeeklyRepoStat[];
  startDate: string;
  endDate: string;
};

type Metric = "net_lines" | "commits";

const LINE_COLORS = [
  "#3b82f6",
  "#10b981",
  "#f59e0b",
  "#ef4444",
  "#8b5cf6",
  "#ec4899",
  "#06b6d4",
  "#f97316",
  "#84cc16",
  "#6366f1",
];

function fmtK(v: number) {
  if (Math.abs(v) >= 1000) return `${(v / 1000).toFixed(1)}k`;
  return String(v);
}

export default function ActivityChart({
  userId,
  repos,
  weeklyByRepo,
  startDate,
  endDate,
}: Props) {
  const router = useRouter();
  const [metric, setMetric] = useState<Metric>("net_lines");

  function handleChange(field: "start_date" | "end_date", value: string) {
    const params = new URLSearchParams({
      start_date: field === "start_date" ? value : startDate,
      end_date: field === "end_date" ? value : endDate,
    });
    router.push(`/users/${userId}?${params.toString()}`);
  }

  // Build chart data: [{week_start, r_<id>: value, ...}]
  const chartData = useMemo(() => {
    const weeks = [...new Set(weeklyByRepo.map((w) => w.week_start))].sort();
    return weeks.map((week) => {
      const entry: Record<string, string | number> = { week_start: week };
      for (const repo of repos) {
        const found = weeklyByRepo.find(
          (w) => w.week_start === week && w.repo_id === repo.repo_id
        );
        entry[`r_${repo.repo_id}`] = found ? found[metric] : 0;
      }
      return entry;
    });
  }, [weeklyByRepo, repos, metric]);

  const shortName = (full: string) => full.split("/").pop() ?? full;

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6">
      {/* Title + controls */}
      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <h2 className="text-lg font-semibold text-gray-900">
          Weekly activity by repository
        </h2>
        <div className="flex items-center gap-3 flex-wrap">
          {/* Metric toggle */}
          <div className="flex gap-1 text-xs">
            <button
              onClick={() => setMetric("net_lines")}
              className={`px-3 py-1.5 rounded-md border transition-colors ${
                metric === "net_lines"
                  ? "bg-blue-600 text-white border-blue-600"
                  : "bg-white text-gray-600 border-gray-300 hover:bg-gray-50"
              }`}
            >
              Net Lines
            </button>
            <button
              onClick={() => setMetric("commits")}
              className={`px-3 py-1.5 rounded-md border transition-colors ${
                metric === "commits"
                  ? "bg-blue-600 text-white border-blue-600"
                  : "bg-white text-gray-600 border-gray-300 hover:bg-gray-50"
              }`}
            >
              Commits
            </button>
          </div>
          {/* Date pickers */}
          <div className="flex items-center gap-2 text-sm">
            <label className="text-gray-500">From</label>
            <input
              type="date"
              value={startDate}
              max={endDate}
              onChange={(e) => handleChange("start_date", e.target.value)}
              className="border border-gray-300 rounded-lg px-3 py-1.5 text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <label className="text-gray-500">To</label>
            <input
              type="date"
              value={endDate}
              min={startDate}
              onChange={(e) => handleChange("end_date", e.target.value)}
              className="border border-gray-300 rounded-lg px-3 py-1.5 text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>
      </div>

      {weeklyByRepo.length === 0 ? (
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
              tickFormatter={(v) => {
                const d = new Date(v + "T00:00:00");
                return `${d.getMonth() + 1}/${d.getDate()}`;
              }}
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
              labelFormatter={(label) => {
                const d = new Date(label + "T00:00:00");
                const day = String(d.getDate()).padStart(2, "0");
                const month = d.toLocaleDateString("en-US", { month: "short" });
                return `Week of ${day} ${month}, ${d.getFullYear()}`;
              }}
              formatter={(value: number, name: string) => {
                const id = parseInt(name.replace("r_", ""), 10);
                const repo = repos.find((r) => r.repo_id === id);
                return [value.toLocaleString("en-US"), shortName(repo?.repo_name ?? name)];
              }}
            />
            <Legend
              formatter={(value: string) => {
                const id = parseInt(value.replace("r_", ""), 10);
                const repo = repos.find((r) => r.repo_id === id);
                return shortName(repo?.repo_name ?? value);
              }}
            />
            {metric === "net_lines" && (
              <ReferenceLine y={0} stroke="#e5e7eb" strokeWidth={1} />
            )}
            {repos.map((repo, i) => (
              <Line
                key={repo.repo_id}
                type="monotone"
                dataKey={`r_${repo.repo_id}`}
                stroke={LINE_COLORS[i % LINE_COLORS.length]}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
