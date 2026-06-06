"use client";
import { useEffect, useState, useRef, useCallback } from "react";
import {
  fetchWPByWeek, fetchWPSummary, fetchWPFilters, fetchPortfolio,
  editWPRow, resetOverrides, fetchSnapshots, saveSnapshotAPI, restoreSnapshotAPI,
} from "@/lib/api";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";

// ── Types ────────────────────────────────────────────────────────────────────
type WPRow = {
  hierarchy_code: number; current_week: number; channel: string;
  written_sales_units: number; written_sales_dollars: number; written_sales_cost: number;
  written_gm_dollar: number; written_gm_perc: number;
  written_aur: number; written_auc: number;
  bop_units: number; eop_units: number;
  total_receipt_units: number; recomm_receipt_units: number;
  on_order_placed_total_unit: number; on_order_unplaced_total_unit: number;
  _modified?: boolean;
};
type PortfolioRow = {
  hierarchy_code: number; l1_name: string; l2_name: string;
  written_sales_units: number; written_sales_dollars: number;
  written_gm_dollar: number; avg_gm_perc: number; _modified: boolean;
};
type Summary = { total_written_sales_units: number; total_written_sales_dollars: number; total_written_gm_dollar: number; avg_written_gm_perc: number };
type Snapshot = { id: number; name: string; created_at: string; overrides_count: number; summary: { total_sales_units: number; total_sales_dollars: number; total_gm_dollar: number; avg_gm_perc: number } };
type Filters = { hierarchies: { hierarchy_code: number; l1_name: string; l2_name: string }[]; channels: string[] };

// ── Formatters ────────────────────────────────────────────────────────────────
const fmtD = (n: number) => n >= 1_000_000 ? `$${(n / 1_000_000).toFixed(2)}M` : n >= 1_000 ? `$${(n / 1_000).toFixed(1)}K` : `$${n.toFixed(0)}`;
const fmtU = (n: number) => Math.round(n).toLocaleString();
const pct  = (n: number) => `${(n * 100).toFixed(1)}%`;
const fmtDelta = (n: number, isDollar = false) => {
  const sign = n > 0 ? "+" : "";
  return isDollar ? `${sign}${fmtD(n)}` : `${sign}${fmtU(n)}`;
};

// ── EditableNumber ────────────────────────────────────────────────────────────
function EditableNumber({
  value, onCommit, isModified, isInteger = true,
}: { value: number; onCommit: (v: number) => void; isModified?: boolean; isInteger?: boolean }) {
  const [editing, setEditing] = useState(false);
  const [inputVal, setInputVal] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const display = isInteger ? fmtU(value) : value.toFixed(2);

  function startEdit() {
    setInputVal(String(isInteger ? Math.round(value) : value.toFixed(2)));
    setEditing(true);
  }

  function commit() {
    setEditing(false);
    const num = parseFloat(inputVal);
    if (!isNaN(num) && num !== value) onCommit(num);
  }

  useEffect(() => { if (editing) inputRef.current?.focus(); }, [editing]);

  if (editing) {
    return (
      <input
        ref={inputRef}
        type="number"
        value={inputVal}
        onChange={(e) => setInputVal(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => { if (e.key === "Enter") commit(); if (e.key === "Escape") setEditing(false); }}
        className="w-20 bg-slate-900 text-white text-right px-1 py-0 text-xs border border-blue-400 rounded outline-none"
      />
    );
  }
  return (
    <span
      onClick={startEdit}
      title="Click to edit"
      className={`cursor-pointer rounded px-1 py-0.5 hover:bg-slate-600 transition-colors select-none ${isModified ? "text-amber-300 font-semibold" : "text-blue-300"}`}
    >
      {display}
      <span className="ml-0.5 text-slate-500 text-[9px]">✎</span>
    </span>
  );
}

// ── Delta badge ───────────────────────────────────────────────────────────────
function Delta({ current, baseline, isDollar = false }: { current: number; baseline: number; isDollar?: boolean }) {
  const diff = current - baseline;
  if (Math.abs(diff) < 0.5) return <span className="text-slate-500 text-[10px]">—</span>;
  const color = diff > 0 ? "text-emerald-400" : "text-red-400";
  return <span className={`text-[10px] font-medium ml-1 ${color}`}>{fmtDelta(diff, isDollar)}</span>;
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function WPPage() {
  const [hc, setHc] = useState("");
  const [ch, setCh] = useState("");
  const [rows, setRows] = useState<WPRow[]>([]);
  const [portfolio, setPortfolio] = useState<PortfolioRow[]>([]);
  const [currentSummary, setCurrentSummary] = useState<Summary | null>(null);
  const [baselineSummary, setBaselineSummary] = useState<Summary | null>(null);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [showSnapshots, setShowSnapshots] = useState(false);
  const [snapshotName, setSnapshotName] = useState("");
  const [filters, setFilters] = useState<Filters>({ hierarchies: [], channels: [] });
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [editError, setEditError] = useState("");

  const canEdit = !!(hc && ch);

  const reloadPortfolioAndSummary = useCallback(async () => {
    const [s, p] = await Promise.all([fetchWPSummary({}), fetchPortfolio()]);
    setCurrentSummary(s);
    setPortfolio(p);
  }, []);

  const reloadRows = useCallback(async () => {
    if (!hc || !ch) { setRows([]); return; }
    const r = await fetchWPByWeek({ hierarchy_code: hc, channel: ch });
    setRows(r);
  }, [hc, ch]);

  // Load baseline + filters + snapshots once
  useEffect(() => {
    fetchWPSummary({ baseline: "true" }).then(setBaselineSummary);
    fetchWPFilters().then(setFilters);
    fetchSnapshots().then(setSnapshots);
    reloadPortfolioAndSummary();
  }, []);

  // Reload rows when hc/ch change
  useEffect(() => { reloadRows(); }, [reloadRows]);

  // Edit handler
  async function handleEdit(week: number, field: string, value: number) {
    if (!canEdit) return;
    setEditError("");
    try {
      const updated = await editWPRow({
        hierarchy_code: parseInt(hc),
        current_week: week,
        channel: ch,
        field,
        value,
      });
      setRows((prev) => prev.map((r) => r.current_week === week ? { ...r, ...updated } : r));
      reloadPortfolioAndSummary();
    } catch (e: unknown) {
      setEditError(e instanceof Error ? e.message : "Edit failed");
    }
  }

  // Save snapshot
  async function handleSaveSnapshot() {
    if (!snapshotName.trim()) return;
    setSaving(true);
    const snap = await saveSnapshotAPI(snapshotName.trim());
    setSnapshots((prev) => [...prev, snap]);
    setSnapshotName("");
    setSaving(false);
  }

  // Reset
  async function handleReset() {
    setResetting(true);
    await resetOverrides();
    await Promise.all([reloadRows(), reloadPortfolioAndSummary()]);
    setResetting(false);
  }

  // Restore snapshot
  async function handleRestore(id: number) {
    await restoreSnapshotAPI(id);
    await Promise.all([reloadRows(), reloadPortfolioAndSummary()]);
    setShowSnapshots(false);
  }

  // Chart data
  const chartData = rows.map((r) => ({
    week: String(r.current_week).slice(-2),
    "Sales U": Math.round(r.written_sales_units),
    "BOP":     Math.round(r.bop_units),
    "EOP":     Math.round(r.eop_units),
    "Receipts": Math.round(r.total_receipt_units),
  }));

  const hasEdits = portfolio.some((p) => p._modified);
  const selectedProduct = filters.hierarchies.find((h) => String(h.hierarchy_code) === hc);

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      {/* ── Header ── */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">Working Plan</h1>
          <p className="text-xs text-slate-500 mt-0.5">FY2025 · click blue values to edit · changes update portfolio in real-time</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {editError && <span className="text-xs text-red-400 bg-red-900/30 px-2 py-1 rounded">{editError}</span>}
          <input
            value={snapshotName}
            onChange={(e) => setSnapshotName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSaveSnapshot()}
            placeholder="Snapshot name…"
            className="bg-slate-800 border border-slate-600 text-xs text-slate-200 rounded px-3 py-1.5 w-40 outline-none focus:border-blue-500"
          />
          <button
            onClick={handleSaveSnapshot}
            disabled={!snapshotName.trim() || saving}
            className="bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white text-xs font-medium px-3 py-1.5 rounded transition-colors"
          >
            {saving ? "Saving…" : "💾 Save Snapshot"}
          </button>
          <button
            onClick={handleReset}
            disabled={!hasEdits || resetting}
            className="bg-slate-700 hover:bg-slate-600 disabled:opacity-40 text-white text-xs px-3 py-1.5 rounded transition-colors"
          >
            {resetting ? "Resetting…" : "↺ Reset All Edits"}
          </button>
          <button
            onClick={() => setShowSnapshots((v) => !v)}
            className={`text-xs px-3 py-1.5 rounded transition-colors border ${showSnapshots ? "bg-violet-700 border-violet-500 text-white" : "bg-slate-800 border-slate-600 text-slate-300 hover:bg-slate-700"}`}
          >
            📸 Snapshots ({snapshots.length})
          </button>
        </div>
      </div>

      {/* ── Filters ── */}
      <div className="flex gap-3 flex-wrap items-center">
        <select
          className="bg-slate-800 border border-slate-600 text-sm text-slate-200 rounded px-3 py-1.5"
          value={hc} onChange={(e) => setHc(e.target.value)}
        >
          <option value="">— Select Hierarchy to Edit —</option>
          {filters.hierarchies.map((h) => (
            <option key={h.hierarchy_code} value={h.hierarchy_code}>{h.l2_name}</option>
          ))}
        </select>
        <select
          className="bg-slate-800 border border-slate-600 text-sm text-slate-200 rounded px-3 py-1.5"
          value={ch} onChange={(e) => setCh(e.target.value)}
        >
          <option value="">— Select Channel —</option>
          {filters.channels.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        {canEdit && (
          <span className="text-xs text-emerald-400 bg-emerald-900/30 border border-emerald-800 px-2 py-1 rounded">
            ✏️ Editing: {selectedProduct?.l2_name} · {ch}
          </span>
        )}
        {!canEdit && (
          <span className="text-xs text-slate-500 border border-slate-700 px-2 py-1 rounded">
            Select hierarchy + channel to enable editing
          </span>
        )}
      </div>

      {/* ── Portfolio KPI cards with deltas ── */}
      {currentSummary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            {
              label: "Portfolio Sales $", val: fmtD(currentSummary.total_written_sales_dollars),
              delta: baselineSummary ? <Delta current={currentSummary.total_written_sales_dollars} baseline={baselineSummary.total_written_sales_dollars} isDollar /> : null,
            },
            {
              label: "Portfolio GM $", val: fmtD(currentSummary.total_written_gm_dollar),
              delta: baselineSummary ? <Delta current={currentSummary.total_written_gm_dollar} baseline={baselineSummary.total_written_gm_dollar} isDollar /> : null,
            },
            {
              label: "GM %", val: pct(currentSummary.avg_written_gm_perc),
              delta: baselineSummary ? <Delta current={currentSummary.avg_written_gm_perc * 100} baseline={baselineSummary.avg_written_gm_perc * 100} /> : null,
            },
            {
              label: "Portfolio Units", val: fmtU(currentSummary.total_written_sales_units),
              delta: baselineSummary ? <Delta current={currentSummary.total_written_sales_units} baseline={baselineSummary.total_written_sales_units} /> : null,
            },
          ].map((k) => (
            <div key={k.label} className={`rounded-lg p-4 border ${hasEdits ? "bg-slate-800 border-amber-900/50" : "bg-slate-800 border-slate-700"}`}>
              <div className="text-xs text-slate-400 mb-1">{k.label}</div>
              <div className="text-xl font-bold text-white">{k.val}</div>
              {k.delta && <div className="mt-1">{k.delta}</div>}
            </div>
          ))}
        </div>
      )}

      {/* ── Portfolio Cross-Product Impact ── */}
      <div className="bg-slate-800 rounded-xl overflow-auto">
        <div className="px-4 pt-4 pb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-300">
            Cross-Product Impact
            {hasEdits && <span className="ml-2 text-xs text-amber-400 bg-amber-900/30 px-1.5 py-0.5 rounded">edits active</span>}
          </h2>
          <span className="text-xs text-slate-500">Click a row to select hierarchy for editing</span>
        </div>
        <table className="w-full text-xs text-slate-300">
          <thead>
            <tr className="border-b border-slate-700 text-slate-400">
              {["", "Product", "Category", "Sales Units", "Sales $", "GM $", "GM %", "Status"].map((h) => (
                <th key={h} className={`px-3 py-2 font-medium ${h === "" || h === "Product" || h === "Category" ? "text-left" : "text-right"}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {portfolio.map((p) => {
              const isSelected = String(p.hierarchy_code) === hc;
              return (
                <tr
                  key={p.hierarchy_code}
                  onClick={() => setHc(String(p.hierarchy_code))}
                  className={`border-b border-slate-700/50 cursor-pointer transition-colors ${
                    isSelected ? "bg-blue-900/30 border-l-2 border-l-blue-500" : "hover:bg-slate-700/40"
                  } ${p._modified ? "bg-amber-900/10" : ""}`}
                >
                  <td className="px-3 py-1.5">
                    {isSelected && <span className="text-blue-400">▶</span>}
                  </td>
                  <td className="px-3 py-1.5 font-medium text-white">{p.l2_name}</td>
                  <td className="px-3 py-1.5 text-slate-400">{p.l1_name}</td>
                  <td className="px-3 py-1.5 text-right">
                    {fmtU(p.written_sales_units)}
                    {p._modified && baselineSummary && (
                      <span className="text-amber-400 text-[10px] ml-1">✎</span>
                    )}
                  </td>
                  <td className="px-3 py-1.5 text-right">{fmtD(p.written_sales_dollars)}</td>
                  <td className="px-3 py-1.5 text-right text-emerald-400">{fmtD(p.written_gm_dollar)}</td>
                  <td className="px-3 py-1.5 text-right">{pct(p.avg_gm_perc)}</td>
                  <td className="px-3 py-1.5 text-right">
                    {p._modified
                      ? <span className="text-amber-400 bg-amber-900/30 px-1.5 py-0.5 rounded text-[10px]">Modified</span>
                      : <span className="text-slate-600 text-[10px]">—</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* ── Chart (when hc+ch selected) ── */}
      {canEdit && rows.length > 0 && (
        <div className="bg-slate-800 rounded-xl p-4">
          <h2 className="text-sm font-semibold text-slate-300 mb-4">
            {selectedProduct?.l2_name} · {ch} — Units by Week
          </h2>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={chartData} margin={{ top: 0, right: 10, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="week" tick={{ fontSize: 10, fill: "#94a3b8" }} />
              <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} />
              <Tooltip contentStyle={{ background: "#1e293b", border: "none", fontSize: 12 }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line type="monotone" dataKey="Sales U" stroke="#3b82f6" dot={false} strokeWidth={2} />
              <Line type="monotone" dataKey="BOP" stroke="#f59e0b" dot={false} strokeWidth={1.5} strokeDasharray="4 2" />
              <Line type="monotone" dataKey="EOP" stroke="#10b981" dot={false} strokeWidth={1.5} strokeDasharray="4 2" />
              <Line type="monotone" dataKey="Receipts" stroke="#8b5cf6" dot={false} strokeWidth={1.5} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* ── Editable detail table ── */}
      <div className="bg-slate-800 rounded-xl overflow-auto">
        <div className="px-4 pt-4 pb-2 flex items-center gap-3">
          <h2 className="text-sm font-semibold text-slate-300">
            {canEdit ? `${selectedProduct?.l2_name} · ${ch}` : "Weekly Detail"}
          </h2>
          {canEdit && (
            <span className="text-xs text-blue-400 bg-blue-900/30 px-2 py-0.5 rounded">
              ✎ blue cells are editable — click to change
            </span>
          )}
        </div>

        {!canEdit ? (
          <p className="text-xs text-slate-500 px-4 pb-4">
            Select a hierarchy and channel above to edit individual week values.
          </p>
        ) : (
          <table className="w-full text-xs text-slate-300">
            <thead>
              <tr className="border-b border-slate-700 text-slate-400">
                {[
                  { label: "Week", align: "left" },
                  { label: "Sales U ✎", align: "right", editable: true },
                  { label: "Sales $ ✎", align: "right", editable: true },
                  { label: "AUC", align: "right" },
                  { label: "AUR", align: "right" },
                  { label: "GM $", align: "right" },
                  { label: "GM %", align: "right" },
                  { label: "OO Placed ✎", align: "right", editable: true },
                  { label: "BOP", align: "right" },
                  { label: "EOP", align: "right" },
                  { label: "Recomm Rcpt", align: "right" },
                ].map((h) => (
                  <th key={h.label} className={`px-3 py-2 font-medium ${h.align === "right" ? "text-right" : "text-left"} ${h.editable ? "text-blue-400" : ""}`}>
                    {h.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.current_week}
                  className={`border-b border-slate-700/50 transition-colors ${r._modified ? "bg-amber-900/10" : "hover:bg-slate-700/20"}`}
                >
                  <td className={`px-3 py-1.5 font-mono ${r._modified ? "text-amber-400" : "text-slate-400"}`}>
                    {r.current_week}
                    {r._modified && <span className="ml-1 text-[9px]">✎</span>}
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    <EditableNumber value={r.written_sales_units} isModified={r._modified}
                      onCommit={(v) => handleEdit(r.current_week, "written_sales_units", v)} />
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    <EditableNumber value={r.written_sales_dollars} isModified={r._modified} isInteger={false}
                      onCommit={(v) => handleEdit(r.current_week, "written_sales_dollars", v)} />
                  </td>
                  <td className="px-3 py-1.5 text-right text-slate-400">{r.written_auc.toFixed(2)}</td>
                  <td className="px-3 py-1.5 text-right text-slate-400">{r.written_aur.toFixed(2)}</td>
                  <td className={`px-3 py-1.5 text-right ${r.written_gm_dollar >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                    {fmtD(r.written_gm_dollar)}
                  </td>
                  <td className={`px-3 py-1.5 text-right ${r.written_gm_perc >= 0.5 ? "text-emerald-400" : r.written_gm_perc >= 0.3 ? "text-slate-300" : "text-amber-400"}`}>
                    {pct(r.written_gm_perc)}
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    <EditableNumber value={r.on_order_placed_total_unit} isModified={r._modified}
                      onCommit={(v) => handleEdit(r.current_week, "on_order_placed_total_unit", v)} />
                  </td>
                  <td className="px-3 py-1.5 text-right">{fmtU(r.bop_units)}</td>
                  <td className="px-3 py-1.5 text-right">{fmtU(r.eop_units)}</td>
                  <td className="px-3 py-1.5 text-right text-violet-400">{fmtU(r.recomm_receipt_units)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* ── Snapshots slide-in panel ── */}
      {showSnapshots && (
        <>
          <div className="fixed inset-0 bg-black/40 z-40" onClick={() => setShowSnapshots(false)} />
          <div className="fixed right-0 top-0 h-full w-80 bg-slate-900 border-l border-slate-700 p-5 overflow-auto z-50 flex flex-col">
            <div className="flex items-center justify-between mb-5">
              <h2 className="font-semibold text-white">Saved Snapshots</h2>
              <button onClick={() => setShowSnapshots(false)} className="text-slate-400 hover:text-white text-lg">✕</button>
            </div>
            {snapshots.length === 0 ? (
              <p className="text-xs text-slate-500">No snapshots saved yet. Edit some values and click "Save Snapshot."</p>
            ) : (
              <div className="space-y-3 flex-1 overflow-auto">
                {[...snapshots].reverse().map((s) => (
                  <div key={s.id} className="bg-slate-800 border border-slate-700 rounded-lg p-3">
                    <div className="font-medium text-white text-sm mb-1">{s.name}</div>
                    <div className="text-[10px] text-slate-500 mb-2">
                      {new Date(s.created_at).toLocaleString()} · {s.overrides_count} edited cell{s.overrides_count !== 1 ? "s" : ""}
                    </div>
                    <div className="grid grid-cols-2 gap-1 mb-3">
                      {[
                        { label: "Sales $", val: fmtD(s.summary.total_sales_dollars) },
                        { label: "GM $",    val: fmtD(s.summary.total_gm_dollar) },
                        { label: "GM %",    val: pct(s.summary.avg_gm_perc) },
                        { label: "Units",   val: fmtU(s.summary.total_sales_units) },
                      ].map((m) => (
                        <div key={m.label} className="bg-slate-700 rounded p-1.5">
                          <div className="text-[9px] text-slate-400">{m.label}</div>
                          <div className="text-xs font-medium text-white">{m.val}</div>
                        </div>
                      ))}
                    </div>
                    <button
                      onClick={() => handleRestore(s.id)}
                      className="w-full text-xs bg-blue-700 hover:bg-blue-600 text-white py-1.5 rounded transition-colors"
                    >
                      Restore this snapshot
                    </button>
                  </div>
                ))}
              </div>
            )}
            {baselineSummary && (
              <div className="mt-4 pt-4 border-t border-slate-700">
                <div className="text-[10px] text-slate-500 mb-2 uppercase tracking-wider">Baseline (original)</div>
                <div className="grid grid-cols-2 gap-1">
                  {[
                    { label: "Sales $", val: fmtD(baselineSummary.total_written_sales_dollars) },
                    { label: "GM $",    val: fmtD(baselineSummary.total_written_gm_dollar) },
                  ].map((m) => (
                    <div key={m.label} className="bg-slate-800 border border-slate-700 rounded p-1.5">
                      <div className="text-[9px] text-slate-500">{m.label}</div>
                      <div className="text-xs text-slate-300">{m.val}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
