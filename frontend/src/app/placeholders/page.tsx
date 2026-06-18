"use client";
import { useEffect, useState, useCallback, useRef } from "react";
import {
  fetchPlaceholders, createPlaceholder, deletePlaceholder, fetchMasterCatalog,
  fetchWPByWeek, fetchWPFilters, editWPRow, undoRowOverride, acceptRecomm, undoRecomm,
  fetchSKUSettings, updateSKUSetting, resetSKUSettings,
  fetchTargetWOS, updateTargetWOS, resetTargetWOS,
  topDownDistribute, undoTopDown,
} from "@/lib/api";

// ── Types ───────────────────────────────────────────────────────────────────────
type Placeholder = { id: number; name: string; source_hc: number; created_at: string; placeholder_hc: number };
type OldSKU = { hierarchy_code: number; l2_name: string; status: string };
type SKUSetting = { hierarchy_code: number; lead_time_weeks: number; case_pack: number; safety_weeks: number; target_wos: number };
type Row = {
  hierarchy_code: number; channel: string; current_week: number;
  written_sales_units: number; written_sales_dollars: number; written_air: number;
  written_dr_perc: number; written_discount_dollars: number; written_aur: number; written_auc: number;
  written_gm_dollar: number; written_gm_perc: number;
  on_order_placed_total_unit: number; oo_locked?: boolean;
  bop_units: number; total_receipt_units: number; eop_units: number;
  recomm_receipt_units: number; wos: number | null; fwd_coverage_wks: number | null;
  lead_time_weeks: number; actualised: boolean; is_ongoing: boolean;
  first_stockout_week?: number | null; _modified?: boolean; _stockout?: boolean;
};

const SELECTABLE_YEARS = [2026, 2027, 2028];

// ── Formatters (leaf, duplicated from the WP page to keep that page untouched) ────
const fmtD = (n: number) => n >= 1_000_000 ? `$${(n / 1_000_000).toFixed(2)}M` : n >= 1_000 ? `$${(n / 1_000).toFixed(1)}K` : `$${n.toFixed(0)}`;
const fmtU = (n: number) => Math.round(n).toLocaleString();
const pct  = (n: number) => `${(n * 100).toFixed(1)}%`;

// ── Editable cells (leaf, duplicated from the WP page) ────────────────────────────
function EditableNumber({ value, onCommit, isModified, isInteger = true, locked = false }:
  { value: number; onCommit: (v: number) => void; isModified?: boolean; isInteger?: boolean; locked?: boolean }) {
  const [editing, setEditing] = useState(false);
  const [inputVal, setInputVal] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => { if (editing) inputRef.current?.focus(); }, [editing]);
  const display = isInteger ? fmtU(value) : value.toFixed(2);
  if (locked) return <span className="text-slate-600 select-none" title="Locked — week not editable">{display}<span className="ml-0.5 text-[9px]">🔒</span></span>;
  function startEdit() { setInputVal(String(isInteger ? Math.round(value) : value.toFixed(2))); setEditing(true); }
  function commit() { setEditing(false); const num = parseFloat(inputVal); if (!isNaN(num) && num !== value) onCommit(num); }
  if (editing) return (
    <input ref={inputRef} type="number" value={inputVal} onChange={(e) => setInputVal(e.target.value)} onBlur={commit}
      onKeyDown={(e) => { if (e.key === "Enter") commit(); if (e.key === "Escape") setEditing(false); }}
      className="w-20 bg-slate-900 text-white text-right px-1 py-0 text-xs border border-blue-400 rounded outline-none" />
  );
  return (
    <span onClick={startEdit} title="Click to edit"
      className={`cursor-pointer rounded px-1 py-0.5 hover:bg-slate-600 transition-colors select-none ${isModified ? "text-amber-300 font-semibold" : "text-blue-300"}`}>
      {display}<span className="ml-0.5 text-slate-500 text-[9px]">✎</span>
    </span>
  );
}

function EditablePercent({ value, onCommit, isModified, locked = false, mode }:
  { value: number; onCommit: (v: number, mode: string) => void; isModified?: boolean; locked?: boolean; mode: string }) {
  const [editing, setEditing] = useState(false);
  const [inputVal, setInputVal] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => { if (editing) inputRef.current?.focus(); }, [editing]);
  if (locked) return <span className="text-slate-600 select-none" title="Locked — week not editable">{pct(value)}<span className="ml-0.5 text-[9px]">🔒</span></span>;
  function startEdit() { setInputVal((value * 100).toFixed(1)); setEditing(true); }
  function commit() { setEditing(false); const num = parseFloat(inputVal); if (!isNaN(num) && num >= 0 && num <= 100 && num / 100 !== value) onCommit(num / 100, mode); }
  if (editing) return (
    <input ref={inputRef} type="number" value={inputVal} min={0} max={100} step={0.1} onChange={(e) => setInputVal(e.target.value)} onBlur={commit}
      onKeyDown={(e) => { if (e.key === "Enter") commit(); if (e.key === "Escape") setEditing(false); }}
      className="w-16 bg-slate-900 text-white text-right px-1 py-0 text-xs border border-blue-400 rounded outline-none" />
  );
  return (
    <span onClick={startEdit} title={`Disc% — click to edit\nMode: ${mode === "hold_units" ? "Hold Units ($ recalcs)" : "Hold $ (Units back-calc)"}`}
      className={`cursor-pointer rounded px-1 py-0.5 hover:bg-slate-600 transition-colors select-none ${isModified ? "text-amber-300 font-semibold" : "text-blue-300"}`}>
      {pct(value)}<span className="ml-0.5 text-slate-500 text-[9px]">✎</span>
    </span>
  );
}

function wosColor(cov: number | null, leadTime: number, targetWos: number | undefined, isForward: boolean, hasStockoutRisk: boolean) {
  if (cov === null || cov === undefined) return "text-slate-500";
  const tw = targetWos && targetWos > 0 ? targetWos : leadTime;
  const lowLine = isForward ? leadTime : tw;
  const excessLine = isForward ? leadTime + tw : tw * 1.5;
  if (cov < lowLine) {
    if (!hasStockoutRisk) return "text-slate-400";
    return cov < lowLine * 0.5 ? "text-red-400 font-semibold" : "text-amber-400";
  }
  if (cov > excessLine) return "text-red-400";
  if (cov > excessLine * 0.85) return "text-amber-400";
  return "text-emerald-400";
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function PlaceholdersPage() {
  const [placeholders, setPlaceholders] = useState<Placeholder[]>([]);
  const [oldSkus, setOldSkus] = useState<OldSKU[]>([]);
  const [name, setName] = useState("");
  const [sourceHc, setSourceHc] = useState<number | "">("");
  const [selected, setSelected] = useState<Placeholder | null>(null);
  const [year, setYear] = useState(2026);
  const [channels, setChannels] = useState<string[]>([]);
  const [channel, setChannel] = useState<string>("");
  const [rows, setRows] = useState<Row[]>([]);
  const [setting, setSetting] = useState<SKUSetting | null>(null);
  const [targetWos, setTargetWos] = useState<number | null>(null);
  const [targetWosOverridden, setTargetWosOverridden] = useState(false);
  const [planningOnly, setPlanningOnly] = useState(false);
  const [discPctMode, setDiscPctMode] = useState<"hold_units" | "hold_dollars">("hold_units");
  const [tdTarget, setTdTarget] = useState("");
  const [tdField, setTdField] = useState<"written_sales_units" | "written_sales_dollars">("written_sales_units");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [toast, setToast] = useState("");
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function flash(m: string) {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToast(m); toastTimer.current = setTimeout(() => setToast(""), 2000);
  }

  const reloadList = useCallback(async () => {
    const [phs, cat] = await Promise.all([fetchPlaceholders(), fetchMasterCatalog()]);
    setPlaceholders(phs);
    setOldSkus((cat as OldSKU[]).filter((s) => s.status === "Old"));
  }, []);

  useEffect(() => { reloadList(); }, [reloadList]);

  // Channel list (from the standard filters payload — channels are shared).
  useEffect(() => {
    fetchWPFilters(year).then((f) => {
      setChannels(f.channels || []);
      setChannel((c) => c || (f.channels?.[0] ?? ""));
    });
  }, [year]);

  const reloadRows = useCallback(async () => {
    if (!selected || !channel) { setRows([]); return; }
    const data = await fetchWPByWeek({
      hierarchy_code: String(selected.placeholder_hc), channel, year: String(year),
    });
    setRows(Array.isArray(data) ? data : []);
  }, [selected, channel, year]);

  useEffect(() => { reloadRows(); }, [reloadRows]);

  const reloadSettings = useCallback(async () => {
    if (!selected) { setSetting(null); setTargetWos(null); return; }
    const [list, tw] = await Promise.all([fetchSKUSettings(), fetchTargetWOS()]);
    setSetting((list as SKUSetting[]).find((s) => s.hierarchy_code === selected.placeholder_hc) ?? null);
    const twRow = (tw as { hierarchy_code: number; channel: string; target_wos: number; is_overridden: boolean }[])
      .find((t) => t.hierarchy_code === selected.placeholder_hc && t.channel === channel);
    setTargetWos(twRow?.target_wos ?? null);
    setTargetWosOverridden(Boolean(twRow?.is_overridden));
  }, [selected, channel]);

  useEffect(() => { reloadSettings(); }, [reloadSettings]);

  async function onCreate() {
    if (!name.trim() || sourceHc === "") return;
    setBusy(true);
    try {
      const ph = await createPlaceholder(name.trim(), Number(sourceHc));
      setName(""); setSourceHc("");
      await reloadList();
      setSelected(ph as Placeholder);
      flash("Placeholder created — seeded from source");
    } finally { setBusy(false); }
  }

  async function onDelete(p: Placeholder) {
    await deletePlaceholder(p.id);
    if (selected?.id === p.id) setSelected(null);
    await reloadList();
    flash("Placeholder deleted");
  }

  async function onEdit(week: number, field: string, value: number, mode?: string) {
    if (!selected) return;
    setErr("");
    try {
      await editWPRow({ hierarchy_code: selected.placeholder_hc, current_week: week, channel, field, value, mode });
      await reloadRows();
      flash("Saved ✓");
    } catch (e) { const m = e instanceof Error ? e.message : "Edit failed"; setErr(m); flash(m); }
  }

  async function onUndoRow(week: number) {
    if (!selected) return;
    await undoRowOverride(selected.placeholder_hc, week, channel);
    await reloadRows();
    flash("Reverted week");
  }

  async function onAcceptRecomm() {
    if (!selected || !channel) return;
    setBusy(true); setErr("");
    try {
      const res = await acceptRecomm({ hierarchy_codes: [selected.placeholder_hc], channels: [channel], year });
      await reloadRows();
      flash(`Accepted recomm — ${res.applied ?? 0} weeks`);
    } catch (e) { const m = e instanceof Error ? e.message : "Accept failed"; setErr(m); flash(m); }
    finally { setBusy(false); }
  }

  async function onUndoRecomm() {
    if (!selected || !channel) return;
    setBusy(true); setErr("");
    try {
      const res = await undoRecomm({ hierarchy_codes: [selected.placeholder_hc], channels: [channel], year });
      await reloadRows();
      flash(`Undid accepted receipts — ${res.cleared ?? 0} weeks`);
    } catch (e) { const m = e instanceof Error ? e.message : "Undo failed"; setErr(m); flash(m); }
    finally { setBusy(false); }
  }

  async function onSettingEdit(field: string, value: number) {
    if (!selected) return;
    setErr("");
    try {
      await updateSKUSetting(selected.placeholder_hc, field, value);
      await Promise.all([reloadSettings(), reloadRows()]);
      flash("Setting updated");
    } catch (e) { const m = e instanceof Error ? e.message : "Setting failed"; setErr(m); flash(m); }
  }

  async function onResetSettings() {
    if (!selected) return;
    await resetSKUSettings(selected.placeholder_hc);
    await Promise.all([reloadSettings(), reloadRows()]);
    flash("Settings reset to source defaults");
  }

  async function onTargetWosEdit(value: number) {
    if (!selected || !channel) return;
    await updateTargetWOS(selected.placeholder_hc, channel, Math.round(value));
    await Promise.all([reloadSettings(), reloadRows()]);
    flash("Target WOS updated");
  }
  async function onResetTargetWos() {
    if (!selected || !channel) return;
    await resetTargetWOS(selected.placeholder_hc, channel);
    await Promise.all([reloadSettings(), reloadRows()]);
    flash("Target WOS reset");
  }

  async function onTopDown() {
    if (!selected || !channel) return;
    const target = parseFloat(tdTarget);
    if (isNaN(target) || target <= 0) { flash("Enter a target > 0"); return; }
    setBusy(true); setErr("");
    try {
      await topDownDistribute({ hierarchy_codes: [selected.placeholder_hc], channels: [channel], target, field: tdField, year });
      await reloadRows();
      flash("Target distributed across planning weeks");
    } catch (e) { const m = e instanceof Error ? e.message : "Distribute failed"; setErr(m); flash(m); }
    finally { setBusy(false); }
  }

  async function onUndoTopDown() {
    if (!selected || !channel) return;
    setBusy(true); setErr("");
    try {
      await undoTopDown({ hierarchy_codes: [selected.placeholder_hc], channels: [channel], year });
      await reloadRows();
      flash("Reverted distribution");
    } catch (e) { const m = e instanceof Error ? e.message : "Undo failed"; setErr(m); flash(m); }
    finally { setBusy(false); }
  }

  const displayRows = rows.filter((r) => !(planningOnly && r.actualised));
  const lt = setting?.lead_time_weeks ?? 12;

  // Summary metrics for the selected placeholder, scoped to the active filters
  // (year + channel — the rows already reflect them). GM% and avg disc% are
  // dollar-weighted (not naive averages). Total cost = revenue − GM (COGS).
  const totals = rows.reduce(
    (a, r) => {
      a.revenue += r.written_sales_dollars;
      a.discount += r.written_discount_dollars;
      a.units += r.written_sales_units;
      a.gm += r.written_gm_dollar;
      a.gross += r.written_sales_dollars + r.written_discount_dollars; // units × AIR
      return a;
    },
    { revenue: 0, discount: 0, units: 0, gm: 0, gross: 0 },
  );
  const totalCost = totals.revenue - totals.gm;
  const gmPerc = totals.revenue > 0 ? totals.gm / totals.revenue : 0;
  const avgDiscPerc = totals.gross > 0 ? totals.discount / totals.gross : 0;
  const cards: { label: string; val: string }[] = [
    { label: "Total Revenue", val: fmtD(totals.revenue) },
    { label: "Total Cost", val: fmtD(totalCost) },
    { label: "GM $", val: `${fmtD(totals.gm)} · ${pct(gmPerc)}` },
    { label: "Total Units", val: fmtU(totals.units) },
    { label: "Total Discount $", val: fmtD(totals.discount) },
    { label: "Avg Disc %", val: pct(avgDiscPerc) },
  ];

  return (
    <div className="max-w-7xl mx-auto pb-16">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white mb-1">Placeholders</h1>
        <p className="text-slate-400 text-sm">
          What-if SKUs cloned from an Old SKU across all years. Edit them exactly like the Working Plan —
          edits are independent of the source and never affect the live portfolio.
        </p>
      </div>

      {/* ── Create + select ── */}
      <div className="bg-slate-800 rounded-xl p-4 mb-5 space-y-4">
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <label className="text-[10px] text-slate-400 block mb-1">Name</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Spring trial"
              className="bg-slate-700 border border-slate-600 text-xs text-slate-200 rounded px-2 py-1.5 w-48" />
          </div>
          <div>
            <label className="text-[10px] text-slate-400 block mb-1">Clone from (Old SKU)</label>
            <select value={sourceHc} onChange={(e) => setSourceHc(e.target.value ? Number(e.target.value) : "")}
              className="bg-slate-700 border border-slate-600 text-xs text-slate-200 rounded px-2 py-1.5">
              <option value="">— pick SKU —</option>
              {oldSkus.map((s) => <option key={s.hierarchy_code} value={s.hierarchy_code}>{s.l2_name} ({s.hierarchy_code})</option>)}
            </select>
          </div>
          <button onClick={onCreate} disabled={!name.trim() || sourceHc === "" || busy}
            className="bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white text-xs font-medium px-3 py-1.5 rounded">
            + Create placeholder
          </button>
        </div>

        {placeholders.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {placeholders.map((p) => (
              <div key={p.id}
                onClick={() => setSelected(selected?.id === p.id ? null : p)}
                className={`flex items-center gap-2 text-xs rounded px-2 py-1 border cursor-pointer ${selected?.id === p.id ? "border-blue-500 bg-blue-900/30 text-white" : "border-slate-600 bg-slate-700/50 text-slate-300"}`}>
                <span className="font-medium">{p.name}</span>
                <span className="text-slate-500">· src {p.source_hc} · #{p.placeholder_hc}</span>
                <button onClick={(e) => { e.stopPropagation(); onDelete(p); }} className="text-red-400 hover:text-red-300" title="Delete placeholder">✕</button>
              </div>
            ))}
          </div>
        )}
      </div>

      {selected == null ? (
        <p className="text-sm text-slate-500 px-1">Select or create a placeholder to edit its plan.</p>
      ) : (
        <>
          {/* ── Toolbar ── */}
          <div className="flex flex-wrap items-end gap-3 mb-3">
            <div>
              <label className="text-[10px] text-slate-400 block mb-1">Year</label>
              <select value={year} onChange={(e) => setYear(Number(e.target.value))}
                className="bg-slate-700 border border-slate-600 text-xs text-slate-200 rounded px-2 py-1.5">
                {SELECTABLE_YEARS.map((y) => <option key={y} value={y}>FY {y}</option>)}
              </select>
            </div>
            <div>
              <label className="text-[10px] text-slate-400 block mb-1">Channel</label>
              <select value={channel} onChange={(e) => setChannel(e.target.value)}
                className="bg-slate-700 border border-slate-600 text-xs text-slate-200 rounded px-2 py-1.5">
                {channels.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <button onClick={onAcceptRecomm} disabled={busy}
              className="bg-emerald-700 hover:bg-emerald-600 disabled:opacity-40 text-white text-xs font-medium px-3 py-1.5 rounded">
              ✓ Accept Recomm
            </button>
            <button onClick={onUndoRecomm} disabled={busy}
              className="bg-slate-700 hover:bg-slate-600 disabled:opacity-40 text-slate-200 text-xs font-medium px-3 py-1.5 rounded">
              ↩ Undo Accepted
            </button>
            <label className="flex items-center gap-1.5 text-xs text-slate-400 cursor-pointer">
              <input type="checkbox" checked={planningOnly} onChange={(e) => setPlanningOnly(e.target.checked)} />
              Planning weeks only
            </label>
            {/* Disc% edit mode — applies to per-cell Disc% edits */}
            <div className="flex items-center gap-1 text-xs text-slate-400">
              <span>Disc% edit:</span>
              <div className="flex rounded overflow-hidden border border-slate-600">
                {(["hold_units", "hold_dollars"] as const).map((m) => (
                  <button key={m} onClick={() => setDiscPctMode(m)}
                    className={`px-2 py-1 ${discPctMode === m ? "bg-blue-600 text-white" : "bg-slate-700 text-slate-300 hover:bg-slate-600"}`}>
                    {m === "hold_units" ? "Hold Units" : "Hold $"}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* ── Target split (top-down distribute by units or $) ── */}
          <div className="flex flex-wrap items-end gap-2 mb-3 bg-slate-800 rounded-xl p-3">
            <span className="text-xs text-slate-400 font-medium self-center">Target split:</span>
            <select value={tdField} onChange={(e) => setTdField(e.target.value as typeof tdField)}
              className="bg-slate-700 border border-slate-600 text-xs text-slate-200 rounded px-2 py-1.5">
              <option value="written_sales_units">Units</option>
              <option value="written_sales_dollars">Dollars</option>
            </select>
            <input value={tdTarget} onChange={(e) => setTdTarget(e.target.value)} type="number" placeholder="total target"
              className="bg-slate-700 border border-slate-600 text-xs text-slate-200 rounded px-2 py-1.5 w-36" />
            <button onClick={onTopDown} disabled={busy}
              className="bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white text-xs font-medium px-3 py-1.5 rounded">
              Distribute across weeks
            </button>
            <button onClick={onUndoTopDown} disabled={busy}
              className="bg-slate-700 hover:bg-slate-600 disabled:opacity-40 text-slate-200 text-xs font-medium px-3 py-1.5 rounded">
              ↩ Undo split
            </button>
            <span className="text-[10px] text-slate-500 self-center">spreads the total across this channel&apos;s planning weeks by seasonal weight</span>
          </div>

          {/* ── Summary cards (respond to year + channel filters) ── */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-4">
            {cards.map((c) => (
              <div key={c.label} className="bg-slate-800 rounded-xl px-3 py-2.5">
                <div className="text-[10px] text-slate-400 mb-1">{c.label}</div>
                <div className="text-sm font-semibold text-slate-100">{c.val}</div>
              </div>
            ))}
          </div>

          {/* ── SKU settings ── */}
          {setting && (
            <div className="bg-slate-800 rounded-xl p-3 mb-3 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs">
              <span className="text-slate-400 font-medium">SKU settings:</span>
              {([["lead_time_weeks", "Lead Time"], ["case_pack", "Case Pack"], ["safety_weeks", "Safety Wks"]] as const).map(([f, label]) => (
                <span key={f} className="text-slate-300">
                  {label}: <EditableNumber value={(setting as unknown as Record<string, number>)[f]} onCommit={(v) => onSettingEdit(f, v)} />
                </span>
              ))}
              <span className="text-slate-300">
                Target WOS: <EditableNumber value={targetWos ?? setting.target_wos} isModified={targetWosOverridden} onCommit={onTargetWosEdit} />
                {targetWosOverridden && <button onClick={onResetTargetWos} className="ml-1 text-red-400 hover:text-red-300" title="Reset channel target WOS">✕</button>}
              </span>
              <button onClick={onResetSettings} className="text-slate-400 hover:text-slate-200 underline">reset all to source</button>
            </div>
          )}

          {err && <div className="text-xs text-red-400 mb-2">{err}</div>}

          {/* ── Plan grid ── */}
          <div className="bg-slate-800 rounded-xl overflow-auto">
            <table className="w-full text-xs text-slate-300">
              <thead>
                <tr className="border-b border-slate-700 text-slate-400 bg-slate-800/80">
                  {[
                    { l: "Week", left: true },
                    { l: "Sales U ✎", edit: true }, { l: "Sales $ ✎", edit: true },
                    { l: "AIR" }, { l: "Disc% ✎", edit: true }, { l: "Disc $" }, { l: "AUR" },
                    { l: "GM $" }, { l: "GM %" },
                    { l: "OO Placed ✎", edit: true }, { l: "BOP" }, { l: "Rcpt" }, { l: "EOP" },
                    { l: "WOS" }, { l: "Fwd Cov" }, { l: "Recomm Rcpt" },
                  ].map((h) => (
                    <th key={h.l} className={`px-3 py-2 font-medium whitespace-nowrap ${h.left ? "text-left" : "text-right"} ${h.edit ? "text-blue-400" : ""}`}>{h.l}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {displayRows.length === 0 && (
                  <tr><td colSpan={16} className="px-3 py-4 text-slate-500">No rows for this channel/year.</td></tr>
                )}
                {displayRows.map((r) => {
                  const locked = r.actualised || r.is_ongoing;
                  const risk = Boolean(r._stockout) || r.first_stockout_week != null;
                  return (
                    <tr key={r.current_week} className="border-b border-slate-700/50 hover:brightness-110 transition-colors">
                      <td className={`px-3 py-1.5 font-mono ${r._modified ? "text-amber-400" : "text-slate-400"}`}>
                        {r.current_week}
                        {r._modified && <button onClick={() => onUndoRow(r.current_week)} title="Undo edits to this week" className="ml-1 text-[9px] text-amber-400 hover:text-red-400">✎↩</button>}
                        {r.actualised && <span className="ml-1 text-[9px] text-violet-400">●</span>}
                        {r.is_ongoing && <span className="ml-1 text-[9px] text-orange-400">⚡</span>}
                      </td>
                      <td className="px-3 py-1.5 text-right">
                        <EditableNumber value={r.written_sales_units} isModified={r._modified} locked={locked}
                          onCommit={(v) => onEdit(r.current_week, "written_sales_units", v)} />
                      </td>
                      <td className="px-3 py-1.5 text-right">
                        <EditableNumber value={r.written_sales_dollars} isModified={r._modified} isInteger={false} locked={locked}
                          onCommit={(v) => onEdit(r.current_week, "written_sales_dollars", v)} />
                      </td>
                      <td className="px-3 py-1.5 text-right text-slate-400">{r.written_air.toFixed(2)}</td>
                      <td className="px-3 py-1.5 text-right">
                        <EditablePercent value={r.written_dr_perc} isModified={r._modified} locked={locked} mode={discPctMode}
                          onCommit={(v, mode) => onEdit(r.current_week, "written_dr_perc", v, mode)} />
                      </td>
                      <td className="px-3 py-1.5 text-right text-orange-300">{fmtD(r.written_discount_dollars)}</td>
                      <td className="px-3 py-1.5 text-right text-slate-300">{r.written_aur.toFixed(2)}</td>
                      <td className={`px-3 py-1.5 text-right ${r.written_gm_dollar >= 0 ? "text-emerald-400" : "text-red-400"}`}>{fmtD(r.written_gm_dollar)}</td>
                      <td className={`px-3 py-1.5 text-right ${r.written_gm_perc >= 0.5 ? "text-emerald-400" : r.written_gm_perc >= 0.3 ? "text-slate-300" : "text-amber-400"}`}>{pct(r.written_gm_perc)}</td>
                      <td className="px-3 py-1.5 text-right" title={r.oo_locked ? "Locked: arrives after season end" : "Order placed this week"}>
                        <EditableNumber value={r.on_order_placed_total_unit} isModified={r._modified} locked={locked || r.oo_locked}
                          onCommit={(v) => onEdit(r.current_week, "on_order_placed_total_unit", v)} />
                      </td>
                      <td className="px-3 py-1.5 text-right">{fmtU(r.bop_units)}</td>
                      <td className="px-3 py-1.5 text-right text-slate-400">{fmtU(r.total_receipt_units)}</td>
                      <td className="px-3 py-1.5 text-right">{fmtU(r.eop_units)}</td>
                      <td className={`px-3 py-1.5 text-right ${wosColor(r.wos, lt, targetWos ?? setting?.target_wos, false, risk)}`}>{r.wos != null ? r.wos.toFixed(1) : "—"}</td>
                      <td className={`px-3 py-1.5 text-right ${wosColor(r.fwd_coverage_wks, lt, targetWos ?? setting?.target_wos, true, risk)}`}>{r.fwd_coverage_wks != null ? r.fwd_coverage_wks.toFixed(1) : "—"}</td>
                      <td className="px-3 py-1.5 text-right text-cyan-300">{fmtU(r.recomm_receipt_units)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {toast && (
        <div className="fixed bottom-6 right-6 z-50 px-4 py-2.5 rounded-lg shadow-xl text-sm font-medium bg-emerald-800 border border-emerald-600 text-emerald-100">
          {toast}
        </div>
      )}
    </div>
  );
}
