"use client";
import { useEffect, useState, useCallback } from "react";
import {
  fetchPlaceholders, createPlaceholder, deletePlaceholder,
  fetchPlaceholderPlan, fetchMasterCatalog,
} from "@/lib/api";

type Placeholder = { id: number; name: string; source_hc: number; created_at: string };
type OldSKU = { hierarchy_code: number; l2_name: string; status: string };
type PlanRow = {
  current_week: number;
  written_sales_units: number;
  written_sales_dollars: number;
  written_dr_perc: number;
  total_receipt_units: number;
};

const fmt$ = (n: number) => n >= 1000 ? `$${(n / 1000).toFixed(1)}K` : `$${n.toFixed(0)}`;

export default function PlaceholdersPanel({ year }: { year: number }) {
  const [open, setOpen] = useState(false);
  const [placeholders, setPlaceholders] = useState<Placeholder[]>([]);
  const [oldSkus, setOldSkus] = useState<OldSKU[]>([]);
  const [name, setName] = useState("");
  const [sourceHc, setSourceHc] = useState<number | "">("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [plan, setPlan] = useState<PlanRow[]>([]);

  const reload = useCallback(async () => {
    const [phs, cat] = await Promise.all([fetchPlaceholders(), fetchMasterCatalog()]);
    setPlaceholders(phs);
    setOldSkus((cat as OldSKU[]).filter((s) => s.status === "Old"));
  }, []);

  useEffect(() => { reload(); }, [reload]);

  // Load the selected placeholder's cloned plan, aggregated by week across channels.
  useEffect(() => {
    if (selectedId == null) { setPlan([]); return; }
    fetchPlaceholderPlan(selectedId, { year: String(year) }).then((rows: PlanRow[]) => {
      const byWk: Record<number, PlanRow> = {};
      for (const r of rows) {
        const w = byWk[r.current_week] ?? {
          current_week: r.current_week, written_sales_units: 0,
          written_sales_dollars: 0, written_dr_perc: 0, total_receipt_units: 0,
        };
        w.written_sales_units += r.written_sales_units;
        w.written_sales_dollars += r.written_sales_dollars;
        w.total_receipt_units += r.total_receipt_units;
        w.written_dr_perc = r.written_dr_perc; // same per week across channels
        byWk[r.current_week] = w;
      }
      setPlan(Object.values(byWk).sort((a, b) => a.current_week - b.current_week));
    });
  }, [selectedId, year]);

  async function onCreate() {
    if (!name.trim() || sourceHc === "") return;
    const ph = await createPlaceholder(name.trim(), Number(sourceHc));
    setName(""); setSourceHc("");
    await reload();
    setSelectedId(ph.id);
  }

  async function onDelete(pid: number) {
    await deletePlaceholder(pid);
    if (selectedId === pid) setSelectedId(null);
    await reload();
  }

  return (
    <div className="bg-slate-800 rounded-xl">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 text-left"
      >
        <span className="text-sm font-semibold text-slate-300">
          Placeholders <span className="text-slate-500 font-normal">— what-if clones of an Old SKU ({placeholders.length})</span>
        </span>
        <span className="text-xs text-slate-500">{open ? "▲ hide" : "▼ show"}</span>
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-4">
          {/* Create */}
          <div className="flex flex-wrap items-end gap-2">
            <div>
              <label className="text-[10px] text-slate-400 block mb-1">Name</label>
              <input
                value={name} onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Spring trial"
                className="bg-slate-700 border border-slate-600 text-xs text-slate-200 rounded px-2 py-1.5 w-48"
              />
            </div>
            <div>
              <label className="text-[10px] text-slate-400 block mb-1">Clone from (Old SKU)</label>
              <select
                value={sourceHc} onChange={(e) => setSourceHc(e.target.value ? Number(e.target.value) : "")}
                className="bg-slate-700 border border-slate-600 text-xs text-slate-200 rounded px-2 py-1.5"
              >
                <option value="">— pick SKU —</option>
                {oldSkus.map((s) => (
                  <option key={s.hierarchy_code} value={s.hierarchy_code}>{s.l2_name} ({s.hierarchy_code})</option>
                ))}
              </select>
            </div>
            <button
              onClick={onCreate} disabled={!name.trim() || sourceHc === ""}
              className="bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white text-xs font-medium px-3 py-1.5 rounded"
            >+ Create placeholder</button>
          </div>

          {/* List */}
          {placeholders.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {placeholders.map((p) => (
                <div
                  key={p.id}
                  className={`flex items-center gap-2 text-xs rounded px-2 py-1 border cursor-pointer ${selectedId === p.id ? "border-blue-500 bg-blue-900/30 text-white" : "border-slate-600 bg-slate-700/50 text-slate-300"}`}
                  onClick={() => setSelectedId(selectedId === p.id ? null : p.id)}
                >
                  <span>{p.name}</span>
                  <span className="text-slate-500">· src {p.source_hc}</span>
                  <button
                    onClick={(e) => { e.stopPropagation(); onDelete(p.id); }}
                    className="text-red-400 hover:text-red-300"
                    title="Delete placeholder"
                  >✕</button>
                </div>
              ))}
            </div>
          )}

          {/* Selected placeholder cloned plan (planning weeks only) */}
          {selectedId != null && plan.length > 0 && (
            <div className="overflow-auto border border-slate-700 rounded">
              <table className="w-full text-xs text-slate-300">
                <thead>
                  <tr className="border-b border-slate-700 text-slate-400">
                    {["Week", "Units", "Sales $", "Disc %", "Receipts"].map((h) => (
                      <th key={h} className="text-right first:text-left px-3 py-1.5 font-medium">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {plan.map((r) => (
                    <tr key={r.current_week} className="border-b border-slate-700/40">
                      <td className="px-3 py-1 font-mono text-slate-400">Wk {String(r.current_week).slice(-2)}</td>
                      <td className="px-3 py-1 text-right">{r.written_sales_units.toLocaleString()}</td>
                      <td className="px-3 py-1 text-right">{fmt$(r.written_sales_dollars)}</td>
                      <td className="px-3 py-1 text-right">{(r.written_dr_perc * 100).toFixed(1)}%</td>
                      <td className="px-3 py-1 text-right">{r.total_receipt_units.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="text-[10px] text-slate-500">
            Placeholders are forward-looking what-if clones (planning weeks only) of an existing
            Old SKU. They persist across sessions and never become real SKUs — delete when done.
          </p>
        </div>
      )}
    </div>
  );
}
