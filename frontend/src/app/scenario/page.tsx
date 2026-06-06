"use client";
import { useEffect, useState } from "react";
import { fetchScenarioCompare, fetchScenarioByWeek, fetchWPFilters } from "@/lib/api";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";

type CompareRow = {
  scenario: number;
  scenario_name: string;
  percent_off: number;
  total_units: number;
  total_dollars: number;
  total_gm: number;
  avg_gm_perc: number;
};

type ByWeekRow = {
  current_week: number;
  scenario: number;
  scenario_name: string;
  percent_off: number;
  total_units: number;
  total_dollars: number;
  total_gm: number;
};

type Filters = { hierarchies: { hierarchy_code: number; l2_name: string }[]; channels: string[] };

const COLORS = ["#3b82f6", "#10b981", "#ef4444", "#f59e0b", "#8b5cf6", "#ec4899", "#06b6d4", "#84cc16", "#f97316", "#a78bfa", "#34d399", "#fb7185"];
const pct = (n: number) => `${(n * 100).toFixed(1)}%`;
const fmt = (n: number) => n >= 1_000_000 ? `$${(n / 1_000_000).toFixed(1)}M` : `$${(n / 1_000).toFixed(0)}K`;

const SCENARIO_NAMES: Record<number, string> = { 0: "Base", 1: "Optimistic", 2: "Pessimistic" };

export default function ScenarioPage() {
  const [compare, setCompare] = useState<CompareRow[]>([]);
  const [byWeek, setByWeek] = useState<ByWeekRow[]>([]);
  const [filters, setFilters] = useState<Filters>({ hierarchies: [], channels: [] });
  const [hc, setHc] = useState("");
  const [ch, setCh] = useState("");
  const [selectedScenario, setSelectedScenario] = useState<number | null>(null);

  async function load() {
    const p: Record<string, string> = {};
    if (hc) p.hierarchy_code = hc;
    if (ch) p.channel = ch;
    const [c, w] = await Promise.all([fetchScenarioCompare(p), fetchScenarioByWeek(p)]);
    setCompare(c);
    setByWeek(w);
  }

  useEffect(() => { fetchWPFilters().then(setFilters); }, []);
  useEffect(() => { load(); }, [hc, ch]);

  // Build chart data: one row per week, columns per (scenario × pct_off) combo
  const pctOffs = [0, 0.10, 0.20, 0.30];
  const scenarios = selectedScenario !== null ? [selectedScenario] : [0, 1, 2];
  const weekSet = Array.from(new Set(byWeek.map((r) => r.current_week))).sort();

  const chartData = weekSet.map((wk) => {
    const row: Record<string, unknown> = { week: String(wk).slice(-2) };
    for (const sc of scenarios) {
      for (const po of pctOffs) {
        const match = byWeek.find(
          (r) => r.current_week === wk && r.scenario === sc && Math.abs(r.percent_off - po) < 0.001
        );
        const key = `${SCENARIO_NAMES[sc]} ${(po * 100).toFixed(0)}% off`;
        row[key] = match?.total_units ?? 0;
      }
    }
    return row;
  });

  const lineKeys: string[] = [];
  for (const sc of scenarios) {
    for (const po of pctOffs) {
      lineKeys.push(`${SCENARIO_NAMES[sc]} ${(po * 100).toFixed(0)}% off`);
    }
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Scenario Planning</h1>
        <span className="text-xs text-slate-500">16-week horizon · dummy data</span>
      </div>

      <div className="flex gap-3 flex-wrap">
        <select className="bg-slate-800 border border-slate-600 text-sm text-slate-200 rounded px-3 py-1.5" value={hc} onChange={(e) => setHc(e.target.value)}>
          <option value="">All Hierarchies</option>
          {filters.hierarchies.map((h) => <option key={h.hierarchy_code} value={h.hierarchy_code}>{h.l2_name}</option>)}
        </select>
        <select className="bg-slate-800 border border-slate-600 text-sm text-slate-200 rounded px-3 py-1.5" value={ch} onChange={(e) => setCh(e.target.value)}>
          <option value="">All Channels</option>
          {filters.channels.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <div className="flex rounded overflow-hidden border border-slate-600 text-sm">
          <button onClick={() => setSelectedScenario(null)} className={`px-3 py-1.5 ${selectedScenario === null ? "bg-blue-600 text-white" : "bg-slate-800 text-slate-300 hover:bg-slate-700"}`}>All</button>
          {[0, 1, 2].map((sc) => (
            <button key={sc} onClick={() => setSelectedScenario(sc === selectedScenario ? null : sc)}
              className={`px-3 py-1.5 ${selectedScenario === sc ? "bg-blue-600 text-white" : "bg-slate-800 text-slate-300 hover:bg-slate-700"}`}
            >{SCENARIO_NAMES[sc]}</button>
          ))}
        </div>
      </div>

      {/* Comparison table */}
      <div className="bg-slate-800 rounded-xl overflow-auto">
        <h2 className="text-sm font-semibold text-slate-300 px-4 pt-4 mb-3">Scenario × Markdown Comparison</h2>
        <table className="w-full text-xs text-slate-300">
          <thead>
            <tr className="border-b border-slate-700 text-slate-400">
              {["Scenario", "% Off", "Total Units", "Total Sales $", "Total GM $", "GM %"].map((h) => (
                <th key={h} className="text-right first:text-left px-3 py-2 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {compare.map((r, i) => (
              <tr key={i} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                <td className="px-3 py-1.5">
                  <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${r.scenario === 0 ? "bg-blue-900 text-blue-300" : r.scenario === 1 ? "bg-emerald-900 text-emerald-300" : "bg-red-900 text-red-300"}`}>{r.scenario_name}</span>
                </td>
                <td className="px-3 py-1.5 text-right">{pct(r.percent_off)}</td>
                <td className="px-3 py-1.5 text-right">{r.total_units.toLocaleString()}</td>
                <td className="px-3 py-1.5 text-right">{fmt(r.total_dollars)}</td>
                <td className={`px-3 py-1.5 text-right ${r.total_gm >= 0 ? "text-emerald-400" : "text-red-400"}`}>{fmt(r.total_gm)}</td>
                <td className={`px-3 py-1.5 text-right ${r.avg_gm_perc >= 0.3 ? "text-emerald-400" : r.avg_gm_perc >= 0.2 ? "text-amber-400" : "text-red-400"}`}>{pct(r.avg_gm_perc)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Line chart */}
      <div className="bg-slate-800 rounded-xl p-4">
        <h2 className="text-sm font-semibold text-slate-300 mb-4">Units by Week — Scenario × Markdown</h2>
        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={chartData} margin={{ top: 0, right: 10, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="week" tick={{ fontSize: 10, fill: "#94a3b8" }} />
            <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} />
            <Tooltip contentStyle={{ background: "#1e293b", border: "none", fontSize: 11 }} />
            <Legend wrapperStyle={{ fontSize: 10 }} />
            {lineKeys.map((k, i) => (
              <Line key={k} type="monotone" dataKey={k} stroke={COLORS[i % COLORS.length]}
                dot={false} strokeWidth={1.5}
                strokeDasharray={k.includes("Pessimistic") ? "4 2" : k.includes("Optimistic") ? "2 2" : undefined}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
