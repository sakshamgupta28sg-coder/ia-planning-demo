"use client";
import { useEffect, useState, useRef, useCallback } from "react";
import {
  fetchWPByWeek, fetchWPSummary, fetchWPFilters, fetchPortfolio,
  editWPRow, resetOverrides, fetchSnapshots, saveSnapshotAPI, restoreSnapshotAPI, deleteSnapshotAPI,
  topDownDistribute, fetchSKUSettings, updateSKUSetting,
} from "@/lib/api";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";

// ── Types ────────────────────────────────────────────────────────────────────
type WPRow = {
  hierarchy_code: number; current_week: number; channel: string;
  written_sales_units: number; written_sales_dollars: number; written_sales_cost: number;
  written_gm_dollar: number; written_gm_perc: number;
  written_aur: number; written_auc: number; written_air: number;
  written_dr_perc: number; written_discount_dollars: number;
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
  // LLY
  lly_sales_units: number; lly_sales_dollars: number;
  lly_units_var: number; lly_dollars_var: number;
  lly_units_var_perc: number; lly_dollars_var_perc: number;
  // Markdown
  markdown_units: number; markdown_dollars: number;
  actualised: boolean;
  is_ongoing: boolean;
  _modified?: boolean;
};
type PortfolioRow = {
  hierarchy_code: number; l1_name: string; l2_name: string;
  written_sales_units: number; written_sales_dollars: number;
  written_gm_dollar: number; avg_gm_perc: number; _modified: boolean;
};
type Summary = { total_written_sales_units: number; total_written_sales_dollars: number; total_written_gm_dollar: number; avg_written_gm_perc: number };
type Snapshot = { id: number; name: string; created_at: string; overrides_count: number; summary: { total_sales_units: number; total_sales_dollars: number; total_gm_dollar: number; avg_gm_perc: number } };
type Filters = {
  hierarchies: { hierarchy_code: number; l1_name: string; l2_name: string; sku_code: string }[];
  channels: string[];
  weeks: number[];
  categories: string[];
};
type SKUSetting = {
  hierarchy_code: number;
  case_pack: number;
  lead_time_weeks: number;
  safety_weeks: number;
  target_wos: number;
};

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
  value, onCommit, isModified, isInteger = true, locked = false,
}: { value: number; onCommit: (v: number) => void; isModified?: boolean; isInteger?: boolean; locked?: boolean }) {
  const [editing, setEditing] = useState(false);
  const [inputVal, setInputVal] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const display = isInteger ? fmtU(value) : value.toFixed(2);

  if (locked) {
    return (
      <span className="text-slate-600 select-none" title="Locked — actualised or ongoing week">
        {display}
        <span className="ml-0.5 text-[9px]">🔒</span>
      </span>
    );
  }

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
  const [selectedCategory, setSelectedCategory] = useState<string>("");
  const [rows, setRows] = useState<WPRow[]>([]);
  const [portfolio, setPortfolio] = useState<PortfolioRow[]>([]);
  const [currentSummary, setCurrentSummary] = useState<Summary | null>(null);
  const [baselineSummary, setBaselineSummary] = useState<Summary | null>(null);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [showSnapshots, setShowSnapshots] = useState(false);
  const [snapshotName, setSnapshotName] = useState("");
  const [filters, setFilters] = useState<Filters>({ hierarchies: [], channels: [], weeks: [], categories: [] });
  const [weekFrom, setWeekFrom] = useState<number | null>(null);
  const [weekTo,   setWeekTo]   = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [editError, setEditError] = useState("");
  const [activeTab, setActiveTab] = useState<"plan" | "actuals" | "inventory" | "ly">("plan");
  const [planningOnly, setPlanningOnly] = useState(false);
  const [topDownTarget, setTopDownTarget] = useState("");
  const [topDownField, setTopDownField] = useState<"written_sales_units" | "written_sales_dollars">("written_sales_units");
  const [topDownLoading, setTopDownLoading] = useState(false);
  const [skuSettings, setSkuSettings] = useState<Record<number, SKUSetting>>({});
  const [discPctMode, setDiscPctMode] = useState<"hold_units" | "hold_dollars">("hold_units");

  // Editing (and viewing weekly detail) requires at least 1 product AND at least 1 channel
  const canEdit = selectedHcs.length >= 1 && selectedChannels.length >= 1;

  // Stable string keys for useCallback dep arrays (avoids array identity issues)
  const hcsKey = [...selectedHcs].sort().join(",");
  const chsKey = [...selectedChannels].sort().join(",");

  // Helper: is a row locked for editing (actualised or in-flight current week)
  const isLocked = (r: WPRow) => r.actualised || r.is_ongoing;
  // Rows visible in the weekly table — respects planning-only toggle + week range filter
  const displayRows = rows.filter((r) => {
    if (planningOnly && isLocked(r)) return false;
    if (weekFrom !== null && r.current_week < weekFrom) return false;
    if (weekTo   !== null && r.current_week > weekTo)   return false;
    return true;
  });

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

  const reloadSkuSettings = useCallback(async () => {
    const list: SKUSetting[] = await fetchSKUSettings();
    setSkuSettings(Object.fromEntries(list.map((s) => [s.hierarchy_code, s])));
  }, []);

  useEffect(() => {
    fetchWPSummary({ baseline: "true" }).then(setBaselineSummary);
    fetchWPFilters().then(setFilters);
    fetchSnapshots().then(setSnapshots);
    reloadPortfolioAndSummary();
    reloadSkuSettings();
  }, []);

  useEffect(() => { reloadRows(); }, [reloadRows]);

  // Toggle a hierarchy in the multi-selection (from table row click)
  function toggleHc(hcStr: string) {
    setSelectedHcs((prev) =>
      prev.includes(hcStr) ? prev.filter((h) => h !== hcStr) : [...prev, hcStr]
    );
  }

  async function handleEdit(hc: number, channel: string, week: number, field: string, value: number, mode?: string) {
    if (!canEdit) return;
    setEditError("");
    try {
      const updated = await editWPRow({ hierarchy_code: hc, current_week: week, channel, field, value, mode });
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

  async function handleSKUSettingEdit(hc: number, field: string, value: number) {
    setEditError("");
    try {
      await updateSKUSetting(hc, field, value);
      await Promise.all([reloadSkuSettings(), reloadRows()]);
    } catch (e: unknown) {
      setEditError(e instanceof Error ? e.message : "SKU setting update failed");
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

  async function handleTopDown() {
    const target = parseFloat(topDownTarget);
    if (isNaN(target) || target <= 0) return;
    setTopDownLoading(true);
    try {
      await topDownDistribute({
        hierarchy_codes: selectedHcs.map(Number),
        channels: selectedChannels,
        target,
        field: topDownField,
      });
      await Promise.all([reloadRows(), reloadPortfolioAndSummary()]);
      setTopDownTarget("");
    } catch (e: unknown) {
      setEditError(e instanceof Error ? e.message : "Top-down failed");
    } finally {
      setTopDownLoading(false);
    }
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

  // Options for multi-select dropdowns — filtered by selected category
  const categoryHierarchies = selectedCategory
    ? filters.hierarchies.filter((h) => h.l1_name === selectedCategory)
    : filters.hierarchies;
  const hcOptions = categoryHierarchies.map((h) => ({
    value: String(h.hierarchy_code),
    label: `${h.sku_code} · ${h.l2_name}`,
  }));
  const chOptions = filters.channels.map((c) => ({ value: c, label: c }));

  // Select all products in the active category
  function selectAllInCategory() {
    setSelectedHcs(categoryHierarchies.map((h) => String(h.hierarchy_code)));
  }

  // Portfolio rows scoped to active category
  const categoryPortfolio = selectedCategory
    ? portfolio.filter((p) => {
        const h = filters.hierarchies.find((h) => h.hierarchy_code === p.hierarchy_code);
        return h?.l1_name === selectedCategory;
      })
    : portfolio;

  // Further filter by selected HCs (for highlighting)
  const visiblePortfolio = selectedHcs.length > 0
    ? categoryPortfolio.filter((p) => selectedHcs.includes(String(p.hierarchy_code)))
    : categoryPortfolio;

  // Build category-grouped portfolio for the table
  const portfolioGroups = (() => {
    const source = categoryPortfolio;
    const seen = new Map<string, { rows: PortfolioRow[]; units: number; dollars: number; gm: number; modified: boolean }>();
    for (const p of source) {
      const h = filters.hierarchies.find((hh) => hh.hierarchy_code === p.hierarchy_code);
      const cat = h?.l1_name ?? "Other";
      if (!seen.has(cat)) seen.set(cat, { rows: [], units: 0, dollars: 0, gm: 0, modified: false });
      const g = seen.get(cat)!;
      g.rows.push(p);
      g.units   += p.written_sales_units;
      g.dollars += p.written_sales_dollars;
      g.gm      += p.written_gm_dollar;
      if (p._modified) g.modified = true;
    }
    return Array.from(seen.entries()).map(([cat, g]) => ({
      cat,
      rows: g.rows,
      units: g.units,
      dollars: g.dollars,
      gm: g.gm,
      gmPerc: g.dollars > 0 ? g.gm / g.dollars : 0,
      modified: g.modified,
    }));
  })();

  // Labels for editing context badge
  const selectedProduct = selectedHcs.length === 1
    ? filters.hierarchies.find((h) => String(h.hierarchy_code) === selectedHcs[0])
    : null;
  const allCategoryHcsSelected =
    selectedCategory &&
    categoryHierarchies.length > 0 &&
    categoryHierarchies.every((h) => selectedHcs.includes(String(h.hierarchy_code)));
  const displayHcLabel =
    selectedHcs.length === 0 ? "No product" :
    allCategoryHcsSelected ? `${selectedCategory} (all)` :
    selectedHcs.length === 1 ? (selectedProduct ? `${selectedProduct.sku_code} · ${selectedProduct.l2_name}` : selectedHcs[0]) :
    `${selectedHcs.length} Products`;
  const displayChLabel = selectedChannels.length === 1
    ? selectedChannels[0]
    : `${selectedChannels.length} Channels`;

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
          <p className="text-xs text-slate-500 mt-0.5">FY2026 · select at least 1 product + 1 channel to edit · edits broadcast to all selected</p>
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

      {/* ── Filters (category → product → channel → week range) ── */}
      <div className="flex gap-3 flex-wrap items-center">
        {/* Category filter */}
        <div className="flex items-center gap-1.5">
          <select
            value={selectedCategory}
            onChange={(e) => {
              const cat = e.target.value;
              setSelectedCategory(cat);
              // Drop selected HCs not in the new category
              if (cat) {
                const catHcs = new Set(
                  filters.hierarchies.filter((h) => h.l1_name === cat).map((h) => String(h.hierarchy_code))
                );
                setSelectedHcs((prev) => prev.filter((h) => catHcs.has(h)));
              }
            }}
            className="bg-slate-800 border border-slate-600 text-sm text-slate-200 rounded px-3 py-1.5 outline-none focus:border-blue-500 cursor-pointer"
          >
            <option value="">All Categories</option>
            {filters.categories.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          {selectedCategory && (
            <button
              onClick={selectAllInCategory}
              title={`Select all ${selectedCategory} products`}
              className="text-xs bg-slate-700 hover:bg-slate-600 border border-slate-600 text-slate-300 px-2.5 py-1.5 rounded transition-colors whitespace-nowrap"
            >
              Select all
            </button>
          )}
        </div>

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

        {/* Week range */}
        <div className="flex items-center gap-1.5">
          <select
            value={weekFrom ?? ""}
            onChange={(e) => setWeekFrom(e.target.value ? Number(e.target.value) : null)}
            className="bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5 outline-none focus:border-blue-500 cursor-pointer"
          >
            <option value="">From week</option>
            {filters.weeks.map((w) => (
              <option key={w} value={w}>Wk {String(w).slice(-2)}</option>
            ))}
          </select>
          <span className="text-slate-600 text-xs">–</span>
          <select
            value={weekTo ?? ""}
            onChange={(e) => setWeekTo(e.target.value ? Number(e.target.value) : null)}
            className="bg-slate-800 border border-slate-600 text-xs text-slate-300 rounded px-2 py-1.5 outline-none focus:border-blue-500 cursor-pointer"
          >
            <option value="">To week</option>
            {filters.weeks.map((w) => (
              <option key={w} value={w}>Wk {String(w).slice(-2)}</option>
            ))}
          </select>
          {(weekFrom !== null || weekTo !== null) && (
            <button
              onClick={() => { setWeekFrom(null); setWeekTo(null); }}
              className="text-xs text-slate-500 hover:text-red-400 px-1 transition-colors"
              title="Clear week filter"
            >✕</button>
          )}
        </div>

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
            {selectedCategory ? `${selectedCategory} · ` : ""}
            {selectedHcs.length > 0 ? `${selectedHcs.length} selected` : "Click rows to select · select all to plan by category"}
          </span>
        </div>
        <table className="w-full text-xs text-slate-300">
          <thead>
            <tr className="border-b border-slate-700 text-slate-400">
              {["", "SKU", "Product", "Sales Units", "Sales $", "GM $", "GM %", "Lead Time ✎", "Case Pack ✎", "Status"].map((h) => (
                <th key={h} className={`px-3 py-2 font-medium ${h === "" || h === "SKU" || h === "Product" ? "text-left" : "text-right"} ${h.includes("✎") ? "text-blue-400" : ""}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {portfolioGroups.map(({ cat, rows: groupRows, units, dollars, gm, gmPerc, modified }) => {
              const allGroupSelected = groupRows.every((p) => selectedHcs.includes(String(p.hierarchy_code)));
              const someGroupSelected = groupRows.some((p) => selectedHcs.includes(String(p.hierarchy_code)));
              return [
                /* Category total row */
                <tr
                  key={`cat-${cat}`}
                  className="bg-slate-700/40 border-b border-slate-600 cursor-pointer hover:bg-slate-700/60 transition-colors"
                  onClick={() => {
                    const hcsInGroup = groupRows.map((p) => String(p.hierarchy_code));
                    if (allGroupSelected) {
                      setSelectedHcs((prev) => prev.filter((h) => !hcsInGroup.includes(h)));
                    } else {
                      setSelectedHcs((prev) => [...new Set([...prev, ...hcsInGroup])]);
                    }
                  }}
                  title={allGroupSelected ? `Deselect all ${cat}` : `Select all ${cat}`}
                >
                  <td className="px-3 py-1.5 w-8">
                    <input
                      type="checkbox"
                      readOnly
                      checked={allGroupSelected}
                      ref={(el) => { if (el) el.indeterminate = !allGroupSelected && someGroupSelected; }}
                      className="accent-blue-500 w-3.5 h-3.5 pointer-events-none"
                    />
                  </td>
                  <td className="px-3 py-1.5 font-semibold text-slate-200 tracking-wide" colSpan={2}>{cat}</td>
                  <td className="px-3 py-1.5 text-right font-semibold text-slate-200">
                    {fmtU(units)}{modified && <span className="text-amber-400 text-[10px] ml-1">✎</span>}
                  </td>
                  <td className="px-3 py-1.5 text-right font-semibold text-slate-200">{fmtD(dollars)}</td>
                  <td className="px-3 py-1.5 text-right font-semibold text-emerald-400">{fmtD(gm)}</td>
                  <td className="px-3 py-1.5 text-right font-semibold">{pct(gmPerc)}</td>
                  <td className="px-3 py-1.5 text-right text-slate-600 text-[10px]">—</td>
                  <td className="px-3 py-1.5 text-right text-slate-600 text-[10px]">—</td>
                  <td className="px-3 py-1.5 text-right">
                    {modified
                      ? <span className="text-amber-400 bg-amber-900/30 px-1.5 py-0.5 rounded text-[10px]">Modified</span>
                      : <span className="text-slate-600 text-[10px]">—</span>}
                  </td>
                </tr>,
                /* Individual SKU rows */
                ...groupRows.map((p) => {
                  const isSelected = selectedHcs.includes(String(p.hierarchy_code));
                  const skuInfo = filters.hierarchies.find((h) => h.hierarchy_code === p.hierarchy_code);
                  return (
                    <tr
                      key={p.hierarchy_code}
                      onClick={() => toggleHc(String(p.hierarchy_code))}
                      className={`border-b border-slate-700/50 cursor-pointer transition-colors ${
                        isSelected ? "bg-blue-900/25" : "hover:bg-slate-700/30"
                      } ${p._modified ? "bg-amber-900/10" : ""}`}
                    >
                      <td className="px-3 py-1.5 w-8 pl-5">
                        <input
                          type="checkbox"
                          readOnly
                          checked={isSelected}
                          className="accent-blue-500 w-3.5 h-3.5 pointer-events-none"
                        />
                      </td>
                      <td className="px-3 py-1.5 font-mono text-slate-400 text-[10px] whitespace-nowrap">
                        {skuInfo?.sku_code ?? "—"}
                      </td>
                      <td className="px-3 py-1.5 text-white pl-4">{p.l2_name}</td>
                      <td className="px-3 py-1.5 text-right">
                        {fmtU(p.written_sales_units)}
                        {p._modified && <span className="text-amber-400 text-[10px] ml-1">✎</span>}
                      </td>
                      <td className="px-3 py-1.5 text-right">{fmtD(p.written_sales_dollars)}</td>
                      <td className="px-3 py-1.5 text-right text-emerald-400">{fmtD(p.written_gm_dollar)}</td>
                      <td className="px-3 py-1.5 text-right">{pct(p.avg_gm_perc)}</td>
                      <td className="px-3 py-1.5 text-right" onClick={(e) => e.stopPropagation()}>
                        <EditableNumber
                          value={skuSettings[p.hierarchy_code]?.lead_time_weeks ?? 0}
                          onCommit={(v) => handleSKUSettingEdit(p.hierarchy_code, "lead_time_weeks", v)}
                        />
                      </td>
                      <td className="px-3 py-1.5 text-right" onClick={(e) => e.stopPropagation()}>
                        <EditableNumber
                          value={skuSettings[p.hierarchy_code]?.case_pack ?? 0}
                          onCommit={(v) => handleSKUSettingEdit(p.hierarchy_code, "case_pack", v)}
                        />
                      </td>
                      <td className="px-3 py-1.5 text-right">
                        {p._modified
                          ? <span className="text-amber-400 bg-amber-900/30 px-1.5 py-0.5 rounded text-[10px]">Modified</span>
                          : <span className="text-slate-600 text-[10px]">—</span>}
                      </td>
                    </tr>
                  );
                }),
              ];
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
          {/* Planning-only toggle */}
          {canEdit && (
            <button
              onClick={() => setPlanningOnly((v) => !v)}
              title="Hide actualised & in-flight weeks, show only editable planning weeks"
              className={`text-xs px-3 py-1 rounded border transition-colors ${
                planningOnly
                  ? "bg-blue-800 border-blue-600 text-blue-200"
                  : "bg-slate-800 border-slate-700 text-slate-400 hover:text-white"
              }`}
            >
              📋 {planningOnly ? "Planning weeks" : "All weeks"}
            </button>
          )}
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
                  {t === "ly" ? "TY/LY/LLY" : t.charAt(0).toUpperCase() + t.slice(1)}
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

        {/* Top-down distribution toolbar (plan tab only) */}
        {canEdit && activeTab === "plan" && (
          <div className="px-4 py-2 border-b border-slate-700 flex flex-wrap items-center gap-2 bg-slate-800/50">
            <span className="text-xs text-slate-400 font-medium">↓ Top-down:</span>
            <input
              value={topDownTarget}
              onChange={(e) => setTopDownTarget(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleTopDown()}
              placeholder="Total target…"
              className="bg-slate-900 border border-slate-700 text-xs text-slate-200 rounded px-2 py-1 w-32 outline-none focus:border-emerald-500"
            />
            <div className="flex rounded overflow-hidden border border-slate-600 text-xs">
              <button
                onClick={() => setTopDownField("written_sales_units")}
                className={`px-3 py-1 transition-colors ${topDownField === "written_sales_units" ? "bg-emerald-700 text-white" : "bg-slate-800 text-slate-400 hover:text-white"}`}
                title="Distribute as total units"
              >Units</button>
              <button
                onClick={() => setTopDownField("written_sales_dollars")}
                className={`px-3 py-1 transition-colors border-l border-slate-600 ${topDownField === "written_sales_dollars" ? "bg-emerald-700 text-white" : "bg-slate-800 text-slate-400 hover:text-white"}`}
                title="Distribute as total sales dollars"
              >$</button>
            </div>
            <button
              onClick={handleTopDown}
              disabled={!topDownTarget.trim() || topDownLoading}
              className="text-xs bg-emerald-700 hover:bg-emerald-600 disabled:opacity-40 text-white px-3 py-1 rounded transition-colors"
            >
              {topDownLoading ? "Applying…" : "Distribute"}
            </button>
            <span className="text-[10px] text-slate-600">
              Distributes total across planning weeks · LY → LLY → plan weights
            </span>
          </div>
        )}

        {/* Disc% edit mode toggle */}
        {canEdit && activeTab === "plan" && (
          <div className="px-4 py-2 border-b border-slate-700 flex flex-wrap items-center gap-2 bg-slate-800/30">
            <span className="text-xs text-slate-400 font-medium">% Disc edit:</span>
            <div className="flex rounded overflow-hidden border border-slate-600 text-xs">
              <button
                onClick={() => setDiscPctMode("hold_units")}
                className={`px-3 py-1 transition-colors ${discPctMode === "hold_units" ? "bg-violet-700 text-white" : "bg-slate-800 text-slate-400 hover:text-white"}`}
                title="Disc% edit keeps units fixed — Sales $ adjusts"
              >
                Hold Units
              </button>
              <button
                onClick={() => setDiscPctMode("hold_dollars")}
                className={`px-3 py-1 transition-colors border-l border-slate-600 ${discPctMode === "hold_dollars" ? "bg-violet-700 text-white" : "bg-slate-800 text-slate-400 hover:text-white"}`}
                title="Disc% edit keeps Sales $ fixed — Units back-calculate"
              >
                Hold $
              </button>
            </div>
            <span className="text-[10px] text-slate-600">
              {discPctMode === "hold_units"
                ? "When Disc% changes → Units stay, Sales $ recalculates"
                : "When Disc% changes → Sales $ stays, Units back-calculates"}
            </span>
          </div>
        )}

        {!canEdit ? (
          <p className="text-xs text-slate-500 px-4 py-4">
            Select at least 1 product and 1 channel above to view and edit weekly values.
          </p>
        ) : (() => {
          // No row shading — plain rows, signal via text/cell colors only
          const weekBgMap = new Map<number, string>();

          return (
          <table className="w-full text-xs text-slate-300">
            <thead>
              <tr className="border-b border-slate-700 text-slate-400 bg-slate-800/80">
                {/* ── PLAN tab ── */}
                {activeTab === "plan" && [
                  { l: "Week", left: true }, { l: "Product", left: true }, { l: "Channel", left: true },
                  { l: "Sales U ✎", edit: true }, { l: "Sales $ ✎", edit: true },
                  { l: "List Price (AIR)" }, { l: "Disc% ✎", edit: true }, { l: "Disc $" }, { l: "AUR" },
                  { l: "AUC" }, { l: "GM $" }, { l: "GM %" },
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
                  { l: "TY U" }, { l: "LY U" }, { l: "TY/LY U%" }, { l: "LLY U" }, { l: "TY/LLY U%" },
                  { l: "TY $" }, { l: "LY $" }, { l: "TY/LY $%" }, { l: "LLY $" }, { l: "TY/LLY $%" },
                ].map((h) => (
                  <th key={h.l} className={`px-3 py-2 font-medium whitespace-nowrap ${h.left ? "text-left" : "text-right"}`}>{h.l}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {displayRows.map((r) => {
                const skuInfo = filters.hierarchies.find((h) => h.hierarchy_code === r.hierarchy_code);
                const weekBg = weekBgMap.get(r.current_week) ?? "";
                const locked = isLocked(r);
                const baseClass = `transition-colors ${weekBg} hover:brightness-110 border-b border-slate-700/50`;
                const wk = (
                  <td className={`px-3 py-1.5 font-mono ${r._modified ? "text-amber-400" : "text-slate-400"}`}>
                    {r.current_week}{r._modified && <span className="ml-1 text-[9px]">✎</span>}
                    {r.actualised && <span className="ml-1 text-[9px] text-violet-400">●</span>}
                    {r.is_ongoing && <span className="ml-1 text-[9px] text-orange-400">⚡</span>}
                  </td>
                );
                const prodCell = (
                  <td className="px-3 py-1.5 whitespace-nowrap">
                    <span className="font-mono text-slate-500 text-[9px] mr-1.5">{skuInfo?.sku_code ?? ""}</span>
                    <span className="text-slate-200">{skuInfo?.l2_name ?? String(r.hierarchy_code)}</span>
                  </td>
                );
                const chCell   = <td className="px-3 py-1.5 text-slate-400 whitespace-nowrap">{r.channel}</td>;
                return (
                  <tr key={`${r.hierarchy_code}_${r.channel}_${r.current_week}`} className={baseClass}>
                    {wk}{prodCell}{chCell}

                    {/* ── PLAN ── */}
                    {activeTab === "plan" && <>
                      <td className="px-3 py-1.5 text-right">
                        <EditableNumber value={r.written_sales_units} isModified={r._modified} locked={locked}
                          onCommit={(v) => handleEdit(r.hierarchy_code, r.channel, r.current_week, "written_sales_units", v)} />
                      </td>
                      <td className="px-3 py-1.5 text-right">
                        <EditableNumber value={r.written_sales_dollars} isModified={r._modified} isInteger={false} locked={locked}
                          onCommit={(v) => handleEdit(r.hierarchy_code, r.channel, r.current_week, "written_sales_dollars", v)} />
                      </td>
                      {/* Pricing block: AIR → Disc% → Disc$ → AUR */}
                      <td className="px-3 py-1.5 text-right text-slate-400" title="Unit List Price (from input files)">{r.written_air.toFixed(2)}</td>
                      <td className="px-3 py-1.5 text-right">
                        {locked ? (
                          <span className="text-slate-600">{pct(r.written_dr_perc)}<span className="ml-0.5 text-[9px]">🔒</span></span>
                        ) : (
                          <span
                            title={`Disc% — Click to edit\nMode: ${discPctMode === "hold_units" ? "Hold Units ($ recalcs)" : "Hold $ (Units back-calc)"}`}
                            className={`cursor-pointer rounded px-1 py-0.5 hover:bg-slate-600 transition-colors select-none ${r._modified ? "text-amber-300 font-semibold" : "text-blue-300"}`}
                            onClick={() => {
                              const input = prompt(
                                `Disc% for wk ${r.current_week}\nMode: ${discPctMode === "hold_units" ? "Hold Units" : "Hold $"}\nCurrent: ${(r.written_dr_perc * 100).toFixed(1)}%\nEnter new % (0–100):`,
                                (r.written_dr_perc * 100).toFixed(1)
                              );
                              if (input === null) return;
                              const pctVal = parseFloat(input);
                              if (isNaN(pctVal) || pctVal < 0 || pctVal > 100) return;
                              handleEdit(r.hierarchy_code, r.channel, r.current_week, "written_dr_perc", pctVal / 100, discPctMode);
                            }}
                          >
                            {pct(r.written_dr_perc)}<span className="ml-0.5 text-slate-500 text-[9px]">✎</span>
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-1.5 text-right text-orange-300" title="Discount $ = Units × AIR × Disc%">{fmtD(r.written_discount_dollars)}</td>
                      <td className="px-3 py-1.5 text-right text-slate-300" title="AUR = AIR × (1 − Disc%)">{r.written_aur.toFixed(2)}</td>
                      <td className="px-3 py-1.5 text-right text-slate-400">{r.written_auc.toFixed(2)}</td>
                      <td className={`px-3 py-1.5 text-right ${r.written_gm_dollar >= 0 ? "text-emerald-400" : "text-red-400"}`}>{fmtD(r.written_gm_dollar)}</td>
                      <td className={`px-3 py-1.5 text-right ${r.written_gm_perc >= 0.5 ? "text-emerald-400" : r.written_gm_perc >= 0.3 ? "text-slate-300" : "text-amber-400"}`}>{pct(r.written_gm_perc)}</td>
                      <td className="px-3 py-1.5 text-right">
                        <EditableNumber value={r.on_order_placed_total_unit} isModified={r._modified} locked={locked}
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
                        <EditableNumber value={r.on_order_placed_total_unit} isModified={r._modified} locked={locked}
                          onCommit={(v) => handleEdit(r.hierarchy_code, r.channel, r.current_week, "on_order_placed_total_unit", v)} />
                      </td>
                      <td className="px-3 py-1.5 text-right text-slate-400">{fmtU(r.on_order_unplaced_total_unit)}</td>
                      <td className="px-3 py-1.5 text-right">{fmtU(r.total_receipt_units)}</td>
                      <td className="px-3 py-1.5 text-right text-violet-400">{fmtU(r.recomm_receipt_units)}</td>
                    </>}

                    {/* ── LY / LLY ── */}
                    {activeTab === "ly" && <>
                      {/* Units block */}
                      <td className="px-3 py-1.5 text-right">{fmtU(r.written_sales_units)}</td>
                      <td className="px-3 py-1.5 text-right text-slate-400">{fmtU(r.ly_sales_units)}</td>
                      <td className={`px-3 py-1.5 text-right font-medium ${lyVarColor(r.ly_units_var_perc)}`}>{pct(r.ly_units_var_perc)}</td>
                      <td className="px-3 py-1.5 text-right text-slate-600">{fmtU(r.lly_sales_units)}</td>
                      <td className={`px-3 py-1.5 text-right font-medium ${lyVarColor(r.lly_units_var_perc)}`}>{pct(r.lly_units_var_perc)}</td>
                      {/* Dollar block */}
                      <td className="px-3 py-1.5 text-right">{fmtD(r.written_sales_dollars)}</td>
                      <td className="px-3 py-1.5 text-right text-slate-400">{fmtD(r.ly_sales_dollars)}</td>
                      <td className={`px-3 py-1.5 text-right font-medium ${lyVarColor(r.ly_dollars_var_perc)}`}>{pct(r.ly_dollars_var_perc)}</td>
                      <td className="px-3 py-1.5 text-right text-slate-600">{fmtD(r.lly_sales_dollars)}</td>
                      <td className={`px-3 py-1.5 text-right font-medium ${lyVarColor(r.lly_dollars_var_perc)}`}>{pct(r.lly_dollars_var_perc)}</td>
                    </>}
                  </tr>
                );
              })}
            </tbody>
          </table>
          );
        })()}

        {/* Legend */}
        {canEdit && rows.length > 0 && (
          <div className="px-4 py-2 border-t border-slate-700 flex flex-wrap gap-4 text-[10px] text-slate-500">
            <span><span className="inline-block w-2 h-2 rounded-full bg-violet-400 mr-1" />● past week (actuals available, locked)</span>
            <span>⚡ ongoing week (in-flight, locked)</span>
            <span>WOS: <span className="text-red-400">red</span> &lt;2 · <span className="text-amber-400">amber</span> &gt;14 · <span className="text-emerald-400">green</span> healthy</span>
            <span>🔒 = cell cannot be edited</span>
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
