"use client";
import { useEffect, useState, useCallback } from "react";
import { fetchMasterCatalog, setMasterTag } from "@/lib/api";

type MasterSKU = {
  hierarchy_code: number;
  l1_name: string;
  l2_name: string;
  sku_code: string | null;
  color: string | null;
  size: string | null;
  air: number | null;
  auc: number | null;
  activation_week: number;
  deactivation_week: number;
  status: "Old" | "New";
  tagged_to: number | null;
};

const wkLabel = (w: number) => `${String(w).slice(0, 4)} W${String(w).slice(-2)}`;

export default function MasterSKUPage() {
  const [rows, setRows] = useState<MasterSKU[]>([]);

  const load = useCallback(async () => {
    setRows(await fetchMasterCatalog());
  }, []);

  useEffect(() => { load(); }, [load]);

  const oldSkus = rows.filter((r) => r.status === "Old");

  async function onTag(hc: number, taggedTo: number | null) {
    await setMasterTag(hc, taggedTo);
    await load();
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Master SKU Catalog</h1>
        <span className="text-xs text-slate-500">read-only · lifecycle + attributes</span>
      </div>

      <p className="text-sm text-slate-400">
        Every SKU (Old + New) with its lifecycle dates and descriptive attributes. A SKU is
        <span className="text-amber-300"> New</span> for its first year after activation (it borrows
        Disc% from a tagged Old SKU during that window), then becomes
        <span className="text-emerald-300"> Old</span> and uses its own history.
      </p>

      <div className="bg-slate-800 rounded-xl overflow-auto">
        <table className="w-full text-xs text-slate-300">
          <thead>
            <tr className="border-b border-slate-700 text-slate-400">
              {["HC", "Category", "Product", "Color", "Size", "AIR", "AUC", "Activated", "Deactivates", "Status", "Borrow Disc% from"].map((h) => (
                <th key={h} className="text-left px-3 py-2 font-medium whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.hierarchy_code} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                <td className="px-3 py-1.5 font-mono text-slate-400">{s.hierarchy_code}</td>
                <td className="px-3 py-1.5">{s.l1_name}</td>
                <td className="px-3 py-1.5">{s.l2_name}</td>
                <td className="px-3 py-1.5">{s.color ?? "—"}</td>
                <td className="px-3 py-1.5">{s.size ?? "—"}</td>
                <td className="px-3 py-1.5">{s.air != null ? `$${s.air.toFixed(2)}` : "—"}</td>
                <td className="px-3 py-1.5">{s.auc != null ? `$${s.auc.toFixed(2)}` : "—"}</td>
                <td className="px-3 py-1.5 font-mono text-slate-400">{wkLabel(s.activation_week)}</td>
                <td className="px-3 py-1.5 font-mono text-slate-400">{wkLabel(s.deactivation_week)}</td>
                <td className="px-3 py-1.5">
                  <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${s.status === "New" ? "bg-amber-900 text-amber-300" : "bg-slate-700 text-slate-300"}`}>
                    {s.status}
                  </span>
                </td>
                <td className="px-3 py-1.5">
                  {s.status === "New" ? (
                    <select
                      value={s.tagged_to ?? ""}
                      onChange={(e) => onTag(s.hierarchy_code, e.target.value ? Number(e.target.value) : null)}
                      className="bg-slate-700 border border-slate-600 text-xs text-slate-200 rounded px-2 py-1 outline-none focus:border-blue-500 cursor-pointer"
                    >
                      <option value="">— none —</option>
                      {oldSkus.map((o) => (
                        <option key={o.hierarchy_code} value={o.hierarchy_code}>
                          {o.l2_name} ({o.hierarchy_code})
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span className="text-slate-600">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
