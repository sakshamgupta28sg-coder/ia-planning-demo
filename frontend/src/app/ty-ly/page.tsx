"use client";
import { useEffect, useState } from "react";
import { fetchTYLYByWeek, fetchTYLYSummary, fetchWPFilters } from "@/lib/api";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  ReferenceLine,
} from "recharts";

type Row = {
  current_week: number;
  ty_units: number; ly_units: number;
  ty_dollars: number; ly_dollars: number;
  units_var: number; units_var_perc: number;
  dollars_var: number; dollars_var_perc: number;
};
type Summary = Record<string, number>;
type Filters = { hierarchies: { hierarchy_code: number; l2_name: string }[]; channels: string[] };

const pct = (n: number) => `${n >= 0 ? "+" : ""}${(n * 100).toFixed(1)}%`;
const fmt = (n: number) => n >= 1_000_000 ? `$${(n / 1_000_000).toFixed(1)}M` : `$${(n / 1_000).toFixed(0)}K`;

export default function TYLYPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [summary, setSummary] = useState<Summary>({});
  const [filters, setFilters] = useState<Filters>({ hierarchies: [], channels: [] });
  const [hc, setHc] = useState("");
  const [ch, setCh] = useState("");
  const [metric, setMetric] = useState<"units" | "dollars">("units");

  async function load() {
    const p: Record<string, string> = {};
    if (hc) p.hierarchy_code = hc;
    if (ch) p.channel = ch;
    const [r, s] = await Promise.all([fetchTYLYByWeek(p), fetchTYLYSummary(p)]);
    setRows(r);
    setSummary(s);
  }

  useEffect(() => { fetchWPFilters().then(setFilters); }, []);
  useEffect(() => { load(); }, [hc, ch]);

  const chartData = rows.map((r) => ({
    week: String(r.current_week).slice(-2),
    TY: metric === "units" ? r.ty_units : r.ty_dollars,
    LY: metric === "units" ? r.ly_units : r.ly_dollars,
    Var: metric === "units" ? r.units_var : r.dollars_var,
  }));

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">TY vs LY</h1>
        <span className="text-xs text-slate-500">FY2025 vs FY2024 · dummy data</span>
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
          {(["units", "dollars"] as const).map((m) => (
            <button key={m} onClick={() => setMetric(m)}
              className={`px-3 py-1.5 ${metric === m ? "bg-blue-600 text-white" : "bg-slate-800 text-slate-300 hover:bg-slate-700"}`}
            >{m === "units" ? "Units" : "Dollars"}</button>
          ))}
        </div>
      </div>

      {/* KPI */}
      {summary.ty_units !== undefined && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: "TY Units", value: summary.ty_units?.toLocaleString() },
            { label: "LY Units", value: summary.ly_units?.toLocaleString() },
            { label: "Units Var", value: pct(summary.units_var_perc), color: summary.units_var_perc >= 0 ? "text-emerald-400" : "text-red-400" },
            { label: "$ Var", value: pct(summary.dollars_var_perc), color: summary.dollars_var_perc >= 0 ? "text-emerald-400" : "text-red-400" },
          ].map((k) => (
            <div key={k.label} className="bg-slate-800 rounded-lg p-4">
              <div className="text-xs text-slate-400 mb-1">{k.label}</div>
              <div className={`text-xl font-bold ${k.color ?? "text-white"}`}>{k.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Chart */}
      <div className="bg-slate-800 rounded-xl p-4">
        <h2 className="text-sm font-semibold text-slate-300 mb-4">
          {metric === "units" ? "Units" : "Dollars"} — TY vs LY by Week
        </h2>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={chartData} margin={{ top: 0, right: 10, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="week" tick={{ fontSize: 10, fill: "#94a3b8" }} />
            <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} />
            <Tooltip contentStyle={{ background: "#1e293b", border: "none", fontSize: 12 }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="TY" fill="#3b82f6" radius={[2, 2, 0, 0]} />
            <Bar dataKey="LY" fill="#64748b" radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Variance chart */}
      <div className="bg-slate-800 rounded-xl p-4">
        <h2 className="text-sm font-semibold text-slate-300 mb-4">Variance (TY − LY)</h2>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={chartData} margin={{ top: 0, right: 10, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="week" tick={{ fontSize: 10, fill: "#94a3b8" }} />
            <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} />
            <Tooltip contentStyle={{ background: "#1e293b", border: "none", fontSize: 12 }} />
            <ReferenceLine y={0} stroke="#475569" />
            <Bar dataKey="Var" fill="#10b981"
              label={false}
              radius={[2, 2, 0, 0]}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Table */}
      <div className="bg-slate-800 rounded-xl overflow-auto">
        <table className="w-full text-xs text-slate-300">
          <thead>
            <tr className="border-b border-slate-700 text-slate-400">
              {["Week", "TY Units", "LY Units", "Units Var", "Units Var %", "TY $", "LY $", "$ Var", "$ Var %"].map((h) => (
                <th key={h} className="text-right first:text-left px-3 py-2 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.current_week} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                <td className="px-3 py-1.5 font-mono">{r.current_week}</td>
                <td className="px-3 py-1.5 text-right">{r.ty_units.toLocaleString()}</td>
                <td className="px-3 py-1.5 text-right">{r.ly_units.toLocaleString()}</td>
                <td className={`px-3 py-1.5 text-right ${r.units_var >= 0 ? "text-emerald-400" : "text-red-400"}`}>{r.units_var >= 0 ? "+" : ""}{r.units_var.toLocaleString()}</td>
                <td className={`px-3 py-1.5 text-right ${r.units_var_perc >= 0 ? "text-emerald-400" : "text-red-400"}`}>{pct(r.units_var_perc)}</td>
                <td className="px-3 py-1.5 text-right">{fmt(r.ty_dollars)}</td>
                <td className="px-3 py-1.5 text-right">{fmt(r.ly_dollars)}</td>
                <td className={`px-3 py-1.5 text-right ${r.dollars_var >= 0 ? "text-emerald-400" : "text-red-400"}`}>{fmt(r.dollars_var)}</td>
                <td className={`px-3 py-1.5 text-right ${r.dollars_var_perc >= 0 ? "text-emerald-400" : "text-red-400"}`}>{pct(r.dollars_var_perc)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
