"use client";
import { useEffect, useState } from "react";
import { fetchSKUs, createSKU, deleteSKU } from "@/lib/api";

type SKU = {
  hierarchy_code: number;
  l1_name: string;
  l2_name: string;
  sku?: string;
  air?: number;
  auc?: number;
  launch_week?: number;
  exit_week?: number;
  lifecycle?: string;
  feed_type?: string;
};

const WEEKS_2025 = Array.from({ length: 52 }, (_, i) => 202501 + i);
const L1_NAMES = ["Trees", "Wreaths", "Garlands", "Ornaments", "Accessories"];

const empty = () => ({
  l1_name: "Trees",
  l2_name: "",
  sku: "",
  air: 0,
  auc: 0,
  launch_week: 202537,
  exit_week: undefined as number | undefined,
  lifecycle: "NEW",
});

export default function SKUsPage() {
  const [existing, setExisting] = useState<SKU[]>([]);
  const [newSkus, setNewSkus] = useState<SKU[]>([]);
  const [form, setForm] = useState(empty());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    const data = await fetchSKUs();
    setExisting(data.existing ?? []);
    setNewSkus(data.new ?? []);
  }

  useEffect(() => { load(); }, []);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!form.l2_name.trim()) { setError("Product name required"); return; }
    if (!form.sku.trim()) { setError("SKU required"); return; }
    if (form.auc >= form.air) { setError("Cost must be less than price"); return; }
    setSaving(true);
    await createSKU(form);
    setForm(empty());
    await load();
    setSaving(false);
  }

  async function handleDelete(hc: number) {
    await deleteSKU(hc);
    await load();
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">New SKUs / Placeholders</h1>
        <span className="text-xs text-slate-500">in-memory · resets on restart</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Add form */}
        <div className="lg:col-span-1">
          <div className="bg-slate-800 rounded-xl p-5">
            <h2 className="text-sm font-semibold text-slate-300 mb-4">Add New SKU</h2>
            <form onSubmit={handleAdd} className="space-y-3">
              <div>
                <label className="text-xs text-slate-400 block mb-1">Category (L1)</label>
                <select className="w-full bg-slate-700 border border-slate-600 text-sm text-slate-200 rounded px-2 py-1.5"
                  value={form.l1_name} onChange={(e) => setForm({ ...form, l1_name: e.target.value })}>
                  {L1_NAMES.map((n) => <option key={n}>{n}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs text-slate-400 block mb-1">Product Name (L2) *</label>
                <input className="w-full bg-slate-700 border border-slate-600 text-sm text-slate-200 rounded px-2 py-1.5"
                  placeholder="e.g. 12ft Flocked Tree" value={form.l2_name}
                  onChange={(e) => setForm({ ...form, l2_name: e.target.value })} />
              </div>
              <div>
                <label className="text-xs text-slate-400 block mb-1">SKU *</label>
                <input className="w-full bg-slate-700 border border-slate-600 text-sm text-slate-200 rounded px-2 py-1.5"
                  placeholder="e.g. BH-9999-US" value={form.sku}
                  onChange={(e) => setForm({ ...form, sku: e.target.value })} />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs text-slate-400 block mb-1">Retail Price (AIR)</label>
                  <input type="number" step="0.01" className="w-full bg-slate-700 border border-slate-600 text-sm text-slate-200 rounded px-2 py-1.5"
                    value={form.air} onChange={(e) => setForm({ ...form, air: parseFloat(e.target.value) || 0 })} />
                </div>
                <div>
                  <label className="text-xs text-slate-400 block mb-1">Unit Cost (AUC)</label>
                  <input type="number" step="0.01" className="w-full bg-slate-700 border border-slate-600 text-sm text-slate-200 rounded px-2 py-1.5"
                    value={form.auc} onChange={(e) => setForm({ ...form, auc: parseFloat(e.target.value) || 0 })} />
                </div>
              </div>
              <div>
                <label className="text-xs text-slate-400 block mb-1">Launch Week</label>
                <select className="w-full bg-slate-700 border border-slate-600 text-sm text-slate-200 rounded px-2 py-1.5"
                  value={form.launch_week} onChange={(e) => setForm({ ...form, launch_week: parseInt(e.target.value) })}>
                  {WEEKS_2025.map((w) => <option key={w} value={w}>{w}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs text-slate-400 block mb-1">Lifecycle</label>
                <select className="w-full bg-slate-700 border border-slate-600 text-sm text-slate-200 rounded px-2 py-1.5"
                  value={form.lifecycle} onChange={(e) => setForm({ ...form, lifecycle: e.target.value })}>
                  {["NEW", "CORE", "EOL"].map((l) => <option key={l}>{l}</option>)}
                </select>
              </div>
              {error && <p className="text-xs text-red-400">{error}</p>}
              <button type="submit" disabled={saving}
                className="w-full bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium py-2 rounded transition-colors disabled:opacity-50">
                {saving ? "Adding…" : "Add SKU"}
              </button>
            </form>
          </div>
        </div>

        {/* Tables */}
        <div className="lg:col-span-2 space-y-5">
          {/* New SKUs */}
          <div className="bg-slate-800 rounded-xl overflow-auto">
            <h2 className="text-sm font-semibold text-slate-300 px-4 pt-4 mb-3">
              New / Placeholder SKUs <span className="text-slate-500">({newSkus.length})</span>
            </h2>
            {newSkus.length === 0 ? (
              <p className="text-xs text-slate-500 px-4 pb-4">No new SKUs added yet.</p>
            ) : (
              <table className="w-full text-xs text-slate-300">
                <thead>
                  <tr className="border-b border-slate-700 text-slate-400">
                    {["HC", "Category", "Product", "SKU", "AIR", "AUC", "IMU", "Launch", ""].map((h) => (
                      <th key={h} className="text-right first:text-left px-3 py-2 font-medium last:text-center">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {newSkus.map((s) => {
                    const imu = s.air && s.auc ? ((s.air - s.auc) / s.air * 100).toFixed(1) : "-";
                    return (
                      <tr key={s.hierarchy_code} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                        <td className="px-3 py-1.5 font-mono text-slate-400">{s.hierarchy_code}</td>
                        <td className="px-3 py-1.5">{s.l1_name}</td>
                        <td className="px-3 py-1.5">{s.l2_name}</td>
                        <td className="px-3 py-1.5 font-mono text-blue-400">{s.sku}</td>
                        <td className="px-3 py-1.5 text-right">${s.air?.toFixed(2)}</td>
                        <td className="px-3 py-1.5 text-right">${s.auc?.toFixed(2)}</td>
                        <td className="px-3 py-1.5 text-right text-emerald-400">{imu}%</td>
                        <td className="px-3 py-1.5 text-right font-mono">{s.launch_week}</td>
                        <td className="px-3 py-1.5 text-center">
                          <button onClick={() => handleDelete(s.hierarchy_code)}
                            className="text-red-400 hover:text-red-300 text-xs px-1.5 py-0.5 rounded hover:bg-red-900/30 transition-colors">
                            Remove
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          {/* Existing catalog */}
          <div className="bg-slate-800 rounded-xl overflow-auto">
            <h2 className="text-sm font-semibold text-slate-300 px-4 pt-4 mb-3">
              Existing Catalog <span className="text-slate-500">({existing.length})</span>
            </h2>
            <table className="w-full text-xs text-slate-300">
              <thead>
                <tr className="border-b border-slate-700 text-slate-400">
                  {["HC", "Category", "Product"].map((h) => (
                    <th key={h} className="text-left px-3 py-2 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {existing.map((s) => (
                  <tr key={s.hierarchy_code} className="border-b border-slate-700/50">
                    <td className="px-3 py-1.5 font-mono text-slate-400">{s.hierarchy_code}</td>
                    <td className="px-3 py-1.5">{s.l1_name}</td>
                    <td className="px-3 py-1.5">{s.l2_name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
