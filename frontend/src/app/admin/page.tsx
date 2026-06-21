"use client";

import { useEffect, useState } from "react";
import { fetchSeedStatus, uploadSeeds } from "../../lib/api";

type Status = {
  source: string;
  seeds_dir: string;
  sku_count: number | null;
  old_skus?: number;
  new_skus?: number;
  budget_rows?: number;
  has_history: boolean;
  history_streams?: number;
  note?: string;
};

const FILES: { key: string; label: string; required: boolean; hint: string }[] = [
  { key: "catalog", label: "catalog.csv", required: true, hint: "SKUs: identity, price, curve, lifecycle" },
  { key: "supply", label: "supply.csv", required: true, hint: "Opening stock + commit posture" },
  { key: "budgets", label: "budgets.csv", required: true, hint: "OTB budget per SKU × channel" },
  { key: "sales_history", label: "sales_history.csv", required: false, hint: "Optional: real TY / LY / LLY sales" },
];

export default function AdminPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [picked, setPicked] = useState<Record<string, File | null>>({});
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadStatus() {
    try {
      setStatus(await fetchSeedStatus());
    } catch (e) {
      setError(String(e));
    }
  }
  useEffect(() => {
    loadStatus();
  }, []);

  const canSubmit = FILES.filter((f) => f.required).every((f) => picked[f.key]) && !busy;

  async function submit() {
    setBusy(true);
    setResult(null);
    setError(null);
    try {
      const form = new FormData();
      for (const f of FILES) {
        const file = picked[f.key];
        if (file) form.append(f.key, file);
      }
      const data = await uploadSeeds(form);
      setResult(
        `Saved ${data.sku_count} SKUs, ${data.budget_rows} budget rows` +
          (data.has_history ? `, ${data.history_rows} history rows` : "") +
          `. ${data.note}`
      );
      loadStatus();
    } catch (e) {
      setError(String(e).replace(/^Error:\s*/, ""));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-3xl font-bold text-white mb-1">Data Import</h1>
      <p className="text-slate-400 text-sm mb-6">
        Upload your seed CSVs to run the tool on your own catalog. Uploads are validated before
        saving — a bad file is rejected and your current data is untouched.
      </p>

      {/* Current seed */}
      <div className="rounded-xl bg-slate-800 border border-slate-700 p-4 mb-6">
        <div className="text-xs uppercase tracking-wide text-slate-500 mb-1">Currently loaded</div>
        {status ? (
          status.source === "demo" ? (
            <div className="text-slate-300 text-sm">Built-in demo data (no catalog.csv present).</div>
          ) : (
            <div className="text-slate-300 text-sm">
              <span className="text-white font-semibold">{status.sku_count} SKUs</span> from CSV ·{" "}
              {status.budget_rows} budget rows ·{" "}
              {status.has_history
                ? `history for ${status.history_streams} streams`
                : "no sales history (parametric curve)"}
              <div className="text-slate-500 text-xs mt-1 font-mono">{status.seeds_dir}</div>
            </div>
          )
        ) : (
          <div className="text-slate-500 text-sm">Loading…</div>
        )}
      </div>

      {/* Upload */}
      <div className="rounded-xl bg-slate-800 border border-slate-700 p-5 space-y-4">
        {FILES.map((f) => (
          <div key={f.key} className="flex items-center justify-between gap-4">
            <div>
              <div className="text-sm font-mono text-white">
                {f.label}
                {f.required ? <span className="text-red-400"> *</span> : <span className="text-slate-500"> (optional)</span>}
              </div>
              <div className="text-xs text-slate-500">{f.hint}</div>
            </div>
            <input
              type="file"
              accept=".csv"
              onChange={(e) => setPicked((p) => ({ ...p, [f.key]: e.target.files?.[0] ?? null }))}
              className="text-xs text-slate-400 file:mr-3 file:rounded file:border-0 file:bg-slate-700 file:px-3 file:py-1.5 file:text-slate-200 hover:file:bg-slate-600"
            />
          </div>
        ))}

        <div className="pt-2 flex items-center gap-3">
          <button
            disabled={!canSubmit}
            onClick={submit}
            className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-40 disabled:cursor-not-allowed hover:bg-blue-500"
          >
            {busy ? "Validating…" : "Upload & Validate"}
          </button>
          <span className="text-xs text-slate-500">catalog, supply, budgets required · sales_history optional</span>
        </div>
      </div>

      {result && (
        <div className="mt-5 rounded-lg border border-emerald-700 bg-emerald-950/40 p-4 text-sm text-emerald-200">
          ✓ {result}
        </div>
      )}
      {error && (
        <div className="mt-5 rounded-lg border border-red-700 bg-red-950/40 p-4 text-sm text-red-200">
          ✗ {error}
        </div>
      )}

      <p className="mt-6 text-xs text-slate-600">
        Need the format? See <span className="font-mono">backend/seeds/README.md</span> and{" "}
        <span className="font-mono">sales_history.csv.template</span>.
      </p>
    </div>
  );
}
