const BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api";

export async function fetchWPByWeek(params?: Record<string, string>) {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  const res = await fetch(`${BASE}/wp/by-week${qs}`, { cache: "no-store" });
  return res.json();
}

export async function fetchWPSummary(params?: Record<string, string>) {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  const res = await fetch(`${BASE}/wp/summary${qs}`, { cache: "no-store" });
  return res.json();
}

export async function fetchWPFilters(year?: number) {
  const qs = year ? `?year=${year}` : "";
  const res = await fetch(`${BASE}/wp/filters${qs}`);
  return res.json();
}

export async function fetchMasterCatalog() {
  const res = await fetch(`${BASE}/wp/master-sku`, { cache: "no-store" });
  return res.json();
}

export async function setMasterTag(hierarchy_code: number, tagged_to: number | null) {
  const res = await fetch(`${BASE}/wp/master-sku/${hierarchy_code}/tag`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tagged_to }),
  });
  return res.json();
}

export async function fetchPlaceholders() {
  const res = await fetch(`${BASE}/wp/placeholders`, { cache: "no-store" });
  return res.json();
}

export async function createPlaceholder(name: string, source_hc: number) {
  const res = await fetch(`${BASE}/wp/placeholders`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, source_hc }),
  });
  return res.json();
}

export async function deletePlaceholder(pid: number) {
  const res = await fetch(`${BASE}/wp/placeholders/${pid}`, { method: "DELETE" });
  return res.json();
}

export async function fetchPlaceholderPlan(pid: number, params?: Record<string, string>) {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  const res = await fetch(`${BASE}/wp/placeholders/${pid}/plan${qs}`, { cache: "no-store" });
  return res.json();
}

export async function fetchPortfolio(params?: Record<string, string>) {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  const res = await fetch(`${BASE}/wp/portfolio${qs}`, { cache: "no-store" });
  return res.json();
}

export async function editWPRow(body: {
  hierarchy_code: number;
  current_week: number;
  channel: string;
  field: string;
  value: number;
  mode?: string;
}) {
  const res = await fetch(`${BASE}/wp/row`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function resetOverrides() {
  await fetch(`${BASE}/wp/overrides`, { method: "DELETE" });
}

export async function fetchSnapshots() {
  const res = await fetch(`${BASE}/wp/snapshots`, { cache: "no-store" });
  return res.json();
}

export async function saveSnapshotAPI(name: string) {
  const res = await fetch(`${BASE}/wp/snapshots`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  return res.json();
}

export async function restoreSnapshotAPI(snap_id: number) {
  await fetch(`${BASE}/wp/snapshots/${snap_id}/restore`, { method: "PUT" });
}

export async function deleteSnapshotAPI(snap_id: number) {
  await fetch(`${BASE}/wp/snapshots/${snap_id}`, { method: "DELETE" });
}

export async function fetchTYLYByWeek(params?: Record<string, string>) {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  const res = await fetch(`${BASE}/ty-ly/by-week${qs}`);
  return res.json();
}

export async function fetchTYLYSummary(params?: Record<string, string>) {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  const res = await fetch(`${BASE}/ty-ly/summary${qs}`);
  return res.json();
}

export async function fetchScenarioCompare(params?: Record<string, string>) {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  const res = await fetch(`${BASE}/scenario/compare${qs}`);
  return res.json();
}

export async function fetchScenarioByWeek(params?: Record<string, string>) {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  const res = await fetch(`${BASE}/scenario/by-week${qs}`);
  return res.json();
}

export async function fetchSKUs() {
  const res = await fetch(`${BASE}/skus`);
  return res.json();
}

export async function createSKU(body: Record<string, unknown>) {
  const res = await fetch(`${BASE}/skus`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

export async function deleteSKU(hierarchy_code: number) {
  const res = await fetch(`${BASE}/skus/${hierarchy_code}`, { method: "DELETE" });
  return res.json();
}

export async function fetchSKUSettings() {
  const res = await fetch(`${BASE}/wp/sku-settings`, { cache: "no-store" });
  return res.json();
}

export async function updateSKUSetting(hierarchy_code: number, field: string, value: number) {
  const res = await fetch(`${BASE}/wp/sku-settings/${hierarchy_code}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ field, value }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function resetSKUSettings(hierarchy_code: number) {
  const res = await fetch(`${BASE}/wp/sku-settings/${hierarchy_code}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchTargetWOS() {
  const res = await fetch(`${BASE}/wp/target-wos`, { cache: "no-store" });
  return res.json();
}

export async function updateTargetWOS(hierarchy_code: number, channel: string, value: number) {
  const res = await fetch(`${BASE}/wp/target-wos/${hierarchy_code}/${channel}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function resetTargetWOS(hierarchy_code: number, channel: string) {
  const res = await fetch(`${BASE}/wp/target-wos/${hierarchy_code}/${channel}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function topDownDistribute(body: {
  hierarchy_codes: number[];
  channels: string[];
  target: number;
  field: string;
  week_values?: { hierarchy_code: number; channel: string; current_week: number; value: number }[];
  year?: number;
}) {
  const res = await fetch(`${BASE}/wp/top-down`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function undoTopDown(body: { hierarchy_codes: number[]; channels: string[]; year?: number }) {
  const res = await fetch(`${BASE}/wp/top-down/undo`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function bulkShiftReceipts(body: {
  hierarchy_codes: number[];
  channels: string[];
  shift_weeks: number;
  year?: number;
}) {
  const res = await fetch(`${BASE}/wp/bulk-shift`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function previewTopDown(body: {
  hierarchy_codes: number[];
  channels: string[];
  target: number;
  field: string;
  year?: number;
}) {
  const res = await fetch(`${BASE}/wp/top-down/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function undoRowOverride(hierarchy_code: number, current_week: number, channel: string) {
  const res = await fetch(`${BASE}/wp/overrides/${hierarchy_code}/${current_week}/${channel}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function compareSnapshots(a: number, b: number) {
  const res = await fetch(`${BASE}/wp/snapshots/compare?a=${a}&b=${b}`, { cache: "no-store" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchExceptions() {
  const res = await fetch(`${BASE}/wp/exceptions`, { cache: "no-store" });
  return res.json();
}

export async function fetchAuditLog(limit = 100, hierarchy_code?: number, field?: string) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (hierarchy_code !== undefined) params.set("hierarchy_code", String(hierarchy_code));
  if (field) params.set("field", field);
  const res = await fetch(`${BASE}/wp/audit?${params}`, { cache: "no-store" });
  return res.json();
}

export async function fetchBudget(params?: Record<string, string>) {
  const qs = params && Object.keys(params).length ? "?" + new URLSearchParams(params).toString() : "";
  const res = await fetch(`${BASE}/wp/budget${qs}`, { cache: "no-store" });
  return res.json();
}

export async function updateBudget(budget: number, params?: Record<string, string>) {
  const qs = params && Object.keys(params).length ? "?" + new URLSearchParams(params).toString() : "";
  const res = await fetch(`${BASE}/wp/budget${qs}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ budget }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function acceptRecomm(body: { hierarchy_codes: number[]; channels: string[]; year?: number }) {
  const res = await fetch(`${BASE}/wp/accept-recomm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function undoRecomm(body: { hierarchy_codes: number[]; channels: string[]; year?: number }) {
  const res = await fetch(`${BASE}/wp/undo-recomm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function fetchSeasonProgress(params?: Record<string, string>) {
  const qs = params && Object.keys(params).length ? "?" + new URLSearchParams(params).toString() : "";
  const res = await fetch(`${BASE}/wp/season-progress${qs}`, { cache: "no-store" });
  return res.json();
}

export async function renameSnapshotAPI(snap_id: number, name: string) {
  const res = await fetch(`${BASE}/wp/snapshots/${snap_id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
