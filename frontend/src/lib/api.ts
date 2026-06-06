const BASE = "http://localhost:8000/api";

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

export async function fetchWPFilters() {
  const res = await fetch(`${BASE}/wp/filters`);
  return res.json();
}

export async function fetchPortfolio() {
  const res = await fetch(`${BASE}/wp/portfolio`, { cache: "no-store" });
  return res.json();
}

export async function editWPRow(body: {
  hierarchy_code: number;
  current_week: number;
  channel: string;
  field: string;
  value: number;
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

export async function topDownDistribute(body: {
  hierarchy_codes: number[];
  channels: string[];
  target: number;
  field: string;
}) {
  const res = await fetch(`${BASE}/wp/top-down`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
