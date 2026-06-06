"use client";
import { useEffect, useState, useRef, useCallback } from "react";
import {
  fetchWPByWeek, fetchWPSummary, fetchWPFilters, fetchPortfolio,
  editWPRow, resetOverrides, fetchSnapshots, saveSnapshotAPI, restoreSnapshotAPI, deleteSnapshotAPI,
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
  // Actuals & variance
  actual_sales_units: number; actual_sales_dollars: number; actual_sales_cost: number;
  variance_units: number | null; variance_dollars: number | null; variance_units_perc: number | null;
  // Inventory analytics
  sell_through_perc: number; wos: number;
  otb_units: number; otb_dollars: number;
  // LY
  ly_sales_units: number; ly_sales_dollars: number;
  ly_units_var: number; ly_dollars_var: number;
  ly_units_var_perc: number; ly_dollars_var_perc: number;
  // Markdown
  markdown_units: number; markdown_dollars: number;
  actualised: boolean;
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

// ── MultiSelect dropdown ──────────────────────────────────────────────────────
function MultiSelect({
  label, options, selected, onChange,
}: {
  label: string;
  options: { value: string; label: string }[];
  selected: string[];
  onChange: (v: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, []);

  const toggle = (val: string) =>
    onChange(selected.includes(val) ? selected.filter((v) => v !== val) : [...selected, val]);

  const displayLabel =
    selected.length === 0 ? `— ${label} —`
    : selected.length === options.length ? `All ${label}s`
    : selected.length === 1 ? (options.find((o) => o.value === selected[0])?.label ?? selected[0])
    : `${selected.length} ${label}s selected`;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className={`bg-slate-800 border text-sm text-slate-200 rounded px-3 py-1.5 flex items-center gap-2 min-w-[200px] justify-between ${
          selected.length > 0 ? "border-blue-500" : "border-slate-600"
        }`}
      >
        <span className={selected.length === 0 ? "text-slate-400" : ""}>{displayLabel}</span>
        <span className="text-slate-400 text-xs">{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <div className="absolute top-full mt-1 left-0 z-50 bg-slate-800 border border-slate-600 rounded-lg shadow-xl min-w-[200px]">
          {options.map((opt) => (
            <label
              key={opt.value}
              className="flex items-center gap-2.5 px-3 py-2 hover:bg-slate-700 cursor-pointer text-sm text-slate-200 first:rounded-t-lg"
            >
              <input
                type="checkbox"
                checked={selected.includes(opt.value)}
                onChange={() => toggle(opt.value)}
                className="accent-blue-500 w-3.5 h-3.5"
              />
              {opt.label}
            </label>
          ))}
          {selected.length > 0 && (
            <button
              onClick={() => { onChange([]); setOpen(false); }}
              className="w-full text-left px-3 py-1.5 text-xs text-slate-500 hover:text-red-400 border-t border-slate-700 rounded-b-lg"
            >
              ✕ Clear selection
            </button>
          )}
        </div>
      )}
    </div>
  );
}

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
  const [selectedHcs, setSelectedHcs] = useState<string[]>([]);
  const [selectedChannels, setSelectedChannels] = useState<string[]>([]);
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
  const [activeTab, setActiveTab] = useState<"plan" | "actuals" | "inventory" | "ly">("plan");

  // Editing (and viewing weekly detail) requires at least 1 product AND at least 1 channel
  const canEdit = selectedHcs.length >= 1 && selectedChannels.length >= 1;

  // Stable string keys for useCallback dep arrays (avoids array identity issues)
  const hcsKey = [...selectedHcs].sort().join(",");
  const chsKey = [...selectedChannels].sort().join(",");

  const reloadPortfolioAndSummary = useCallback(async () => {
    const [s, p] = await Promise.all([fetchWPSummary({}), fetchPortfolio()]);
    setCurrentSummary(s);
    setPortfolio(p);
  }, []);

  const reloadRows = useCallback(async () => {
    if (!canEdit) { setRows([]); return; }

    // Always fetch each product × channel combo individually so rows keep their identity
    const combos = selectedHcs.flatMap((hc) => selectedChannels.map((ch) => ({ hc, ch })));
    const allFetches = await Promise.all(
      combos.map(({ hc, ch }) => fetchWPByWeek({ hierarchy_code: hc, channel: ch }))
    );
    const flat = (allFetches.flat() as WPRow[]).sort(
      (a, b) => a.current_week - b.current_week || a.hierarchy_code - b.hierarchy_code || a.channel.localeCompare(b.channel)
    );
    setRows(flat);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canEdit, hcsKey, chsKey]);

  useEffect(() => {
    fetchWPSummary({ baseline: "true" }).then(setBaselineSummary);
    fetchWPFilters().then(setFilters);
    fetchSnapshots().then(setSnapshots);
    reloadPortfolioAndSummary();
  }, []);

  useEffect(() => { reloadRows(); }, [reloadRows]);

  // Toggle a hierarchy in the multi-selection (from table row click)
  function toggleHc(hcStr: string) {
    setSelectedHcs((prev) =>
      prev.includes(hcStr) ? prev.filter((h) => h !== hcStr) : [...prev, hcStr]
    );
  }

  async function handleEdit(hc: number, channel: string, week: number, field: string, value: number) {
    if (!canEdit) return;
    setEditError("");
    try {
      const updated = await editWPRow({ hierarchy_code: hc, current_week: week, channel, field, value });
      setRows((prev) =>
        prev.map((r) =>
          r.current_week === week && r.hierarchy_code === hc && r.channel === channel
            ? { ...r, ...updated }
            : r
        )
      );
      reloadPortfolioAndSummary();
    } catch (e: unknown) {
      setEditError(e instanceof Error ? e.message : "Edit failed");
    }
  }

  async function handleSaveSnapshot() {
    if (!snapshotName.trim()) return;
    setSaving(true);
    const snap = await saveSnapshotAPI(snapshotName.trim());
    setSnapshots((prev) => [...prev, snap]);
    setSnapshotName("");
    setSaving(false);
  }

  async function handleReset() {
    setResetting(true);
    await resetOverrides();
    await Promise.all([reloadRows(), reloadPortfolioAndSummary()]);
    setResetting(false);
  }

  async function handleRestore(id: number) {
    await restoreSnapshotAPI(id);
    await Promise.all([reloadRows(), reloadPortfolioAndSummary()]);
    setShowSnapshots(false);
  }

  async function handleDeleteSnapshot(id: number) {
    await deleteSnapshotAPI(id);
    setSnapshots((prev) => prev.filter((s) => s.id !== id));
  }

  // Aggregate rows by week for the chart (multiple product×channel rows share the same week)
  const chartData = (() => {
    const byWeek = new Map<number, { week: string; "Sales U": number; BOP: number; EOP: number; Receipts: number }>();
    for (const r of rows) {
      const wk = r.current_week;
      if (!byWeek.has(wk)) byWeek.set(wk, { week: String(wk).slice(-2), "Sales U": 0, BOP: 0, EOP: 0, Receipts: 0 });
      const w = byWeek.get(wk)!;
      w["Sales U"] += Math.round(r.written_sales_units);
      w["BOP"]     += Math.round(r.bop_units);
      w["EOP"]     += Math.round(r.eop_units);
      w["Receipts"]+= Math.round(r.total_receipt_units);
    }
    return Array.from(byWeek.values()).sort((a, b) => parseInt(a.week) - parseInt(b.week));
  })();

  const hasEdits = portfolio.some((p) => p._modified);
  const selectedProduct = selectedHcs.length === 1
    ? filters.hierarchies.find((h) => String(h.hierarchy_code) === selectedHcs[0])
    : null;
  const displayHcLabel = selectedHcs.length === 1
    ? (selectedProduct?.l2_name ?? selectedHcs[0])
    : `${selectedHcs.length} Products`;
  const displayChLabel = selectedChannels.length === 1
    ? selectedChannels[0]
    : `${selectedChannels.length} Channels`;

  // Options for multi-select dropdowns
  const hcOptions = filters.hierarchies.map((h) => ({
    value: String(h.hierarchy_code),
    label: h.l2_name,
  }));
  const chOptions = filters.channels.map((c) => ({ value: c, label: c }));

  // Filter portfolio table by selected hierarchies (if any)
  const visiblePortfolio = selectedHcs.length > 0
    ? portfolio.filter((p) => selectedHcs.includes(String(p.hierarchy_code)))
    : portfolio;

  // ── Exception / coloring helpers ─────────────────────────────────────────────
  // variance = Plan − Actual: positive = below plan = BAD (red), negative = above plan = GOOD (green)
  function varPctColor(v: number | null) {
    if (v === null) return "text-slate-500";
    if (v > 0.15)  return "text-red-400";     // actual badly below plan
    if (v > 0.05)  return "text-amber-400";   // actual slightly below plan
    if (v < -0.05) return "text-emerald-400"; // actual above plan
    return "text-slate-300";
  }
  // TY/LY variance = TY − LY: positive = TY grew vs LY = GOOD (green)
  function lyVarColor(v: number | null) {
    if (v === null) return "text-slate-500";
    if (v > 0.05)  return "text-emerald-400"; // TY above LY
    if (v < -0.05) return "text-red-400";     // TY below LY
    return "text-slate-300";
  }
  function wosColor(w: number) {
    if (w < 2)  return "text-red-400 font-semibold";
    if (w < 4)  return "text-amber-400";
    if (w > 16) return "text-red-400";
    if (w > 12) return "text-amber-400";
    return "text-emerald-400";
  }
  function stColor(st: number) {
    if (st > 0.6) return "text-emerald-400";
    if (st > 0.4) return "text-slate-300";
    return "text-amber-400";
  }
  function rowExceptionBg(r: WPRow) {
    if (r.actualised && r.variance_units_perc !== null) {
      if (r.variance_units_perc > 0.15)  return "bg-red-900/20";    // actual badly below plan
      if (r.variance_units_perc < -0.1)  return "bg-emerald-900/15"; // actual above plan
    }
    if (r.wos > 14) return "bg-amber-900/15";
    if (r.wos > 0 && r.wos < 2) return "bg-red-900/15";
    if (r._modified) return "bg-amber-900/10";
    return "";
  }

  // ── CSV export ────────────────────────────────────────────────────────────────
  function exportCSV() {
    const hdrs = ["Week","Product","Channel",
      "Plan U","Plan $","Act U","Act $","Var U","Var U%","ST%",
      "WOS","OTB U","OTB $","GM $","GM %","MD U","MD $",
      "BOP","EOP","OO Placed","Recomm Rcpt",
      "LY U","LY $","TY/LY U%","TY/LY $%"];
    const csv = [
      hdrs.join(","),
      ...rows.map((r) => {
        const prod = filters.hierarchies.find((h) => h.hierarchy_code === r.hierarchy_code)?.l2_name ?? String(r.hierarchy_code);
        return [
          r.current_week, `"${prod}"`, r.channel,
          r.written_sales_units, r.written_sales_dollars,
          r.actual_sales_units, r.actual_sales_dollars,
          r.variance_units ?? "",
          r.variance_units_perc !== null ? `${(r.variance_units_perc * 100).toFixed(1)}%` : "",
          r.actualised ? `${(r.sell_through_perc * 100).toFixed(1)}%` : "",
          r.wos, r.otb_units, r.otb_dollars,
          r.written_gm_dollar, `${(r.written_gm_perc * 100).toFixed(1)}%`,
          r.markdown_units, r.markdown_dollars,
          r.bop_units, r.eop_units, r.on_order_placed_total_unit, r.recomm_receipt_units,
          r.ly_sales_units, r.ly_sales_dollars,
          `${(r.ly_units_var_perc * 100).toFixed(1)}%`, `${(r.ly_dollars_var_perc * 100).toFixed(1)}%`,
        ].join(",");
      }),
    ].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url; a.download = `wp-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click(); URL.revokeObjectURL(url);
  }

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      {/* ── Header ── */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">Working Plan</h1>
          <p className="text-xs text-slate-500 mt-0.5">FY2025 · select at least 1 product + 1 channel to edit · edits broadcast to all selected</p>
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

      {/* ── Filters (multi-select) ── */}
      <div className="flex gap-3 flex-wrap items-center">
        <MultiSelect
          label="Product"
          options={hcOptions}
          selected={selectedHcs}
          onChange={setSelectedHcs}
        />
        <MultiSelect
          label="Channel"
          options={chOptions}
          selected={selectedChannels}
          onChange={setSelectedChannels}
        />
        {canEdit && (
          <span className="text-xs text-emerald-400 bg-emerald-900/30 border border-emerald-800 px-2 py-1 rounded">
            ✏️ Editing: {displayHcLabel} · {displayChLabel}
          </span>
        )}
        {!canEdit && (
          <span className="text-xs text-slate-500 border border-slate-700 px-2 py-1 rounded">
            Select at least 1 product + 1 channel to enable editing
          </span>
        )}
      </div>

      {/* ── Portfolio KPI cards ── */}
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

      {/* ── Cross-Product Impact table ── */}
      <div className="bg-slate-800 rounded-xl overflow-auto">
        <div className="px-4 pt-4 pb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-300">
            Cross-Product Impact
            {hasEdits && <span className="ml-2 text-xs text-amber-400 bg-amber-900/30 px-1.5 py-0.5 rounded">edits active</span>}
          </h2>
          <span className="text-xs text-slate-500">
            {selectedHcs.length > 0 ? `${visiblePortfolio.length} of ${portfolio.length} products` : "Click rows to filter · select 1 to edit"}
          </span>
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
            {(visiblePortfolio.length > 0 ? visiblePortfolio : portfolio).map((p) => {
              const isSelected = selectedHcs.includes(String(p.hierarchy_code));
              return (
                <tr
                  key={p.hierarchy_code}
                  onClick={() => toggleHc(String(p.hierarchy_code))}
                  className={`border-b border-slate-700/50 cursor-pointer transition-colors ${
                    isSelected ? "bg-blue-900/30" : "hover:bg-slate-700/40"
                  } ${p._modified ? "bg-amber-900/10" : ""}`}
                >
                  <td className="px-3 py-1.5 w-8">
                    <input
                      type="checkbox"
                      readOnly
                      checked={isSelected}
                      className="accent-blue-500 w-3.5 h-3.5 pointer-events-none"
                    />
                  </td>
                  <td className="px-3 py-1.5 font-medium text-white">{p.l2_name}</td>
                  <td className="px-3 py-1.5 text-slate-400">{p.l1_name}</td>
                  <td className="px-3 py-1.5 text-right">
                    {fmtU(p.written_sales_units)}
                    {p._modified && <span className="text-amber-400 text-[10px] ml-1">✎</span>}
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

      {/* ── Chart (when product + channel selected) ── */}
      {canEdit && rows.length > 0 && (
        <div className="bg-slate-800 rounded-xl p-4">
          <h2 className="text-sm font-semibold text-slate-300 mb-4">
            {displayHcLabel} · {displayChLabel} — Units by Week
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

      {/* ── Weekly detail table ── */}
      <div className="bg-slate-800 rounded-xl overflow-auto">
        {/* Header bar */}
        <div className="px-4 pt-4 pb-2 flex flex-wrap items-center gap-3 border-b border-slate-700">
          <h2 className="text-sm font-semibold text-slate-300">
            {canEdit ? `${displayHcLabel} · ${displayChLabel}` : "Weekly Detail"}
          </h2>
          {canEdit && (
            <span className="text-xs text-blue-400 bg-blue-900/30 px-2 py-0.5 rounded">
              ✎ blue cells are editable
            </span>
          )}
          <div className="flex-1" />
          {/* Tab buttons */}
          {canEdit && (
            <div className="flex gap-1">
              {(["plan","actuals","inventory","ly"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setActiveTab(t)}
                  className={`text-xs px-3 py-1 rounded capitalize transition-colors ${
                    activeTab === t
                      ? "bg-blue-600 text-white"
                      : "bg-slate-700 text-slate-400 hover:text-white"
                  }`}
                >
                  {t === "ly" ? "TY/LY" : t.charAt(0).toUpperCase() + t.slice(1)}
                </button>
              ))}
            </div>
          )}
          {/* Export */}
          {canEdit && rows.length > 0 && (
            <button
              onClick={exportCSV}
              className="text-xs bg-slate-700 hover:bg-slate-600 text-slate-300 px-3 py-1 rounded transition-colors"
              title="Export visible data to CSV"
            >
              ⬇ CSV
            </button>
          )}
        </div>

        {!canEdit ? (
          <p className="text-xs text-slate-500 px-4 py-4">
            Select at least 1 product and 1 channel above to view and edit weekly values.
          </p>
        ) : (
          <table className="w-full text-xs text-slate-300">
            <thead>
              <tr className="border-b border-slate-700 text-slate-400 bg-slate-800/80">
                {/* ── PLAN tab ── */}
                {activeTab === "plan" && [
                  { l: "Week", left: true }, { l: "Product", left: true }, { l: "Channel", left: true },
                  { l: "Sales U ✎", edit: true }, { l: "Sales $ ✎", edit: true },
                  { l: "AUC" }, { l: "AUR" }, { l: "GM $" }, { l: "GM %" },
                  { l: "OO Placed ✎", edit: true }, { l: "BOP" }, { l: "EOP" },
                  { l: "WOS" }, { l: "Recomm Rcpt" },
                ].map((h) => (
                  <th key={h.l} className={`px-3 py-2 font-medium whitespace-nowrap ${h.left ? "text-left" : "text-right"} ${h.edit ? "text-blue-400" : ""}`}>{h.l}</th>
                ))}
                {/* ── ACTUALS tab ── */}
                {activeTab === "actuals" && [
                  { l: "Week", left: true }, { l: "Product", left: true }, { l: "Channel", left: true },
                  { l: "Plan U" }, { l: "Plan $" },
                  { l: "Act U" }, { l: "Act $" },
                  { l: "Var U" }, { l: "Var U%" },
                  { l: "Var $" }, { l: "Var $%" },
                  { l: "ST%" }, { l: "MD U" }, { l: "MD $" },
                ].map((h) => (
                  <th key={h.l} className={`px-3 py-2 font-medium whitespace-nowrap ${h.left ? "text-left" : "text-right"}`}>{h.l}</th>
                ))}
                {/* ── INVENTORY tab ── */}
                {activeTab === "inventory" && [
                  { l: "Week", left: true }, { l: "Product", left: true }, { l: "Channel", left: true },
                  { l: "BOP" }, { l: "EOP" }, { l: "WOS" },
                  { l: "OTB U" }, { l: "OTB $" },
                  { l: "OO Placed ✎", edit: true }, { l: "OO Unplaced" },
                  { l: "Rcpt Total" }, { l: "Recomm Rcpt" },
                ].map((h) => (
                  <th key={h.l} className={`px-3 py-2 font-medium whitespace-nowrap ${h.left ? "text-left" : "text-right"} ${h.edit ? "text-blue-400" : ""}`}>{h.l}</th>
                ))}
                {/* ── LY tab ── */}
                {activeTab === "ly" && [
                  { l: "Week", left: true }, { l: "Product", left: true }, { l: "Channel", left: true },
                  { l: "TY U" }, { l: "LY U" }, { l: "Var U" }, { l: "TY/LY U%" },
                  { l: "TY $" }, { l: "LY $" }, { l: "Var $" }, { l: "TY/LY $%" },
                ].map((h) => (
                  <th key={h.l} className={`px-3 py-2 font-medium whitespace-nowrap ${h.left ? "text-left" : "text-right"}`}>{h.l}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const prod = filters.hierarchies.find((h) => h.hierarchy_code === r.hierarchy_code)?.l2_name ?? String(r.hierarchy_code);
                const exBg = rowExceptionBg(r);
                const baseClass = `transition-colors ${exBg || "hover:bg-slate-700/20"} border-b border-slate-700/50`;
                const wk = (
                  <td className={`px-3 py-1.5 font-mono ${r._modified ? "text-amber-400" : "text-slate-400"}`}>
                    {r.current_week}{r._modified && <span className="ml-1 text-[9px]">✎</span>}
                    {r.actualised && <span className="ml-1 text-[9px] text-violet-400">●</span>}
                  </td>
                );
                const prodCell = <td className="px-3 py-1.5 text-slate-200 whitespace-nowrap">{prod}</td>;
                const chCell   = <td className="px-3 py-1.5 text-slate-400 whitespace-nowrap">{r.channel}</td>;
                return (
                  <tr key={`${r.hierarchy_code}_${r.channel}_${r.current_week}`} className={baseClass}>
                    {wk}{prodCell}{chCell}

                    {/* ── PLAN ── */}
                    {activeTab === "plan" && <>
                      <td className="px-3 py-1.5 text-right">
                        <EditableNumber value={r.written_sales_units} isModified={r._modified}
                          onCommit={(v) => handleEdit(r.hierarchy_code, r.channel, r.current_week, "written_sales_units", v)} />
                      </td>
                      <td className="px-3 py-1.5 text-right">
                        <EditableNumber value={r.written_sales_dollars} isModified={r._modified} isInteger={false}
                          onCommit={(v) => handleEdit(r.hierarchy_code, r.channel, r.current_week, "written_sales_dollars", v)} />
                      </td>
                      <td className="px-3 py-1.5 text-right text-slate-400">{r.written_auc.toFixed(2)}</td>
                      <td className="px-3 py-1.5 text-right text-slate-400">{r.written_aur.toFixed(2)}</td>
                      <td className={`px-3 py-1.5 text-right ${r.written_gm_dollar >= 0 ? "text-emerald-400" : "text-red-400"}`}>{fmtD(r.written_gm_dollar)}</td>
                      <td className={`px-3 py-1.5 text-right ${r.written_gm_perc >= 0.5 ? "text-emerald-400" : r.written_gm_perc >= 0.3 ? "text-slate-300" : "text-amber-400"}`}>{pct(r.written_gm_perc)}</td>
                      <td className="px-3 py-1.5 text-right">
                        <EditableNumber value={r.on_order_placed_total_unit} isModified={r._modified}
                          onCommit={(v) => handleEdit(r.hierarchy_code, r.channel, r.current_week, "on_order_placed_total_unit", v)} />
                      </td>
                      <td className="px-3 py-1.5 text-right">{fmtU(r.bop_units)}</td>
                      <td className="px-3 py-1.5 text-right">{fmtU(r.eop_units)}</td>
                      <td className={`px-3 py-1.5 text-right ${wosColor(r.wos)}`}>{r.wos}</td>
                      <td className="px-3 py-1.5 text-right text-violet-400">{fmtU(r.recomm_receipt_units)}</td>
                    </>}

                    {/* ── ACTUALS ── */}
                    {activeTab === "actuals" && <>
                      <td className="px-3 py-1.5 text-right">{fmtU(r.written_sales_units)}</td>
                      <td className="px-3 py-1.5 text-right">{fmtD(r.written_sales_dollars)}</td>
                      {r.actualised ? <>
                        <td className="px-3 py-1.5 text-right text-blue-300">{fmtU(r.actual_sales_units)}</td>
                        <td className="px-3 py-1.5 text-right text-blue-300">{fmtD(r.actual_sales_dollars)}</td>
                        <td className={`px-3 py-1.5 text-right ${varPctColor(r.variance_units_perc)}`}>{r.variance_units !== null ? fmtU(r.variance_units) : "—"}</td>
                        <td className={`px-3 py-1.5 text-right ${varPctColor(r.variance_units_perc)}`}>{r.variance_units_perc !== null ? pct(r.variance_units_perc) : "—"}</td>
                        <td className={`px-3 py-1.5 text-right ${varPctColor(r.variance_units_perc)}`}>{r.variance_dollars !== null ? fmtD(r.variance_dollars) : "—"}</td>
                        <td className={`px-3 py-1.5 text-right ${varPctColor(r.variance_units_perc)}`}>
                          {r.variance_dollars !== null && r.written_sales_dollars > 0
                            ? pct(r.variance_dollars / r.written_sales_dollars)
                            : "—"}
                        </td>
                        <td className={`px-3 py-1.5 text-right ${stColor(r.sell_through_perc)}`}>{pct(r.sell_through_perc)}</td>
                      </> : <>
                        {[...Array(7)].map((_, i) => <td key={i} className="px-3 py-1.5 text-right text-slate-600">—</td>)}
                      </>}
                      <td className="px-3 py-1.5 text-right text-slate-400">{fmtU(r.markdown_units)}</td>
                      <td className="px-3 py-1.5 text-right text-slate-400">{fmtD(r.markdown_dollars)}</td>
                    </>}

                    {/* ── INVENTORY ── */}
                    {activeTab === "inventory" && <>
                      <td className="px-3 py-1.5 text-right">{fmtU(r.bop_units)}</td>
                      <td className="px-3 py-1.5 text-right">{fmtU(r.eop_units)}</td>
                      <td className={`px-3 py-1.5 text-right ${wosColor(r.wos)}`}>{r.wos}</td>
                      <td className="px-3 py-1.5 text-right text-cyan-400">{fmtU(r.otb_units)}</td>
                      <td className="px-3 py-1.5 text-right text-cyan-400">{fmtD(r.otb_dollars)}</td>
                      <td className="px-3 py-1.5 text-right">
                        <EditableNumber value={r.on_order_placed_total_unit} isModified={r._modified}
                          onCommit={(v) => handleEdit(r.hierarchy_code, r.channel, r.current_week, "on_order_placed_total_unit", v)} />
                      </td>
                      <td className="px-3 py-1.5 text-right text-slate-400">{fmtU(r.on_order_unplaced_total_unit)}</td>
                      <td className="px-3 py-1.5 text-right">{fmtU(r.total_receipt_units)}</td>
                      <td className="px-3 py-1.5 text-right text-violet-400">{fmtU(r.recomm_receipt_units)}</td>
                    </>}

                    {/* ── LY ── */}
                    {activeTab === "ly" && <>
                      <td className="px-3 py-1.5 text-right">{fmtU(r.written_sales_units)}</td>
                      <td className="px-3 py-1.5 text-right text-slate-400">{fmtU(r.ly_sales_units)}</td>
                      <td className={`px-3 py-1.5 text-right ${lyVarColor(r.ly_units_var_perc)}`}>{fmtU(r.ly_units_var)}</td>
                      <td className={`px-3 py-1.5 text-right font-medium ${lyVarColor(r.ly_units_var_perc)}`}>{pct(r.ly_units_var_perc)}</td>
                      <td className="px-3 py-1.5 text-right">{fmtD(r.written_sales_dollars)}</td>
                      <td className="px-3 py-1.5 text-right text-slate-400">{fmtD(r.ly_sales_dollars)}</td>
                      <td className={`px-3 py-1.5 text-right ${lyVarColor(r.ly_dollars_var_perc)}`}>{fmtD(r.ly_dollars_var)}</td>
                      <td className={`px-3 py-1.5 text-right font-medium ${lyVarColor(r.ly_dollars_var_perc)}`}>{pct(r.ly_dollars_var_perc)}</td>
                    </>}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}

        {/* Legend */}
        {canEdit && rows.length > 0 && (
          <div className="px-4 py-2 border-t border-slate-700 flex gap-4 text-[10px] text-slate-500">
            <span><span className="inline-block w-2 h-2 rounded-full bg-violet-400 mr-1" />● past (actuals available)</span>
            <span><span className="inline-block w-2 h-2 rounded-full bg-red-600 mr-1" />red row = below plan &gt;15% or WOS&lt;2</span>
            <span><span className="inline-block w-2 h-2 rounded-full bg-amber-600 mr-1" />amber row = WOS&gt;14</span>
            <span><span className="inline-block w-2 h-2 rounded-full bg-emerald-700 mr-1" />green row = tracking above plan</span>
          </div>
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
                    <div className="flex items-start justify-between gap-2 mb-1">
                      <div className="font-medium text-white text-sm">{s.name}</div>
                      <button
                        onClick={() => handleDeleteSnapshot(s.id)}
                        title="Delete snapshot"
                        className="text-slate-500 hover:text-red-400 text-sm transition-colors flex-shrink-0"
                      >
                        🗑
                      </button>
                    </div>
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
