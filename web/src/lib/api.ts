import { bootstrapSchema, importPreviewSchema, whatIfSchema, type Bootstrap } from "./schema";

export type WhatIf = Awaited<ReturnType<typeof whatIf>>;

async function fetchJson(url: string, init?: RequestInit): Promise<unknown> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), 6000);
  let res: Response;
  try {
    res = await fetch(url, { ...init, signal: ctl.signal });
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      body = await res.text();
    }
    throw new Error(typeof body === "string" ? body : JSON.stringify(body));
  }
  return res.json();
}

export async function loadBootstrap(): Promise<{ data: Bootstrap; fromFallback: boolean }> {
  try {
    const raw = await fetchJson("/api/bootstrap");
    return { data: bootstrapSchema.parse(raw), fromFallback: false };
  } catch {
    const raw = await fetchJson("/fallback/bootstrap.json");
    return { data: bootstrapSchema.parse(raw), fromFallback: true };
  }
}

export async function previewImportFile(file: File) {
  const fd = new FormData();
  fd.append("file", file);
  const raw = await fetchJson("/api/import/preview", { method: "POST", body: fd });
  return importPreviewSchema.parse(raw);
}

export async function commitImportFile(file: File) {
  const fd = new FormData();
  fd.append("file", file);
  const raw = await fetchJson("/api/import/commit", { method: "POST", body: fd });
  return bootstrapSchema.parse(raw);
}

export async function previewImportText(filename: string, csvText: string) {
  const fd = new FormData();
  fd.append("filename", filename);
  fd.append("csv_text", csvText);
  const raw = await fetchJson("/api/import/preview-text", { method: "POST", body: fd });
  return importPreviewSchema.parse(raw);
}

export async function whatIf(resultId: number, quantity: number) {
  const raw = await fetchJson("/api/what-if", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ result_id: resultId, quantity }),
  });
  return whatIfSchema.parse(raw);
}

export function exportUrl(snapshotId: number) {
  return `/api/export/${snapshotId}`;
}

export async function closeGap() {
  const raw = await fetchJson("/api/demo/close-gap", { method: "POST" });
  return bootstrapSchema.parse(raw);
}

export async function resetDemo() {
  const raw = await fetchJson("/api/reset", { method: "POST" });
  return bootstrapSchema.parse(raw);
}

/** Offline recount: emissions are linear in quantity, so scaling the stored result is exact. UI says "offline". */
export function localWhatIf(r: any, qty: number, categoryKg: number | null, totalKg: number | null): WhatIf {
  const base = Number(r.input_quantity_snapshot);
  const after = base > 0 ? (r.result_value * qty) / base : null;
  const delta = after == null ? 0 : after - r.result_value;
  const factorText = (r.plain_formula ?? "").match(/× (.+?) =/)?.[1] ?? "";
  const n = (v: number) => v.toLocaleString("en-US", { maximumFractionDigits: 2 });
  return {
    ok: true, result_id: r.id, quantity_before: base, quantity_after: qty, unit: r.input_unit_snapshot,
    kg_before: r.result_value, kg_after: after, status: "calculated",
    plain_formula: after == null ? null : `${n(qty)} ${r.input_unit_snapshot} × ${factorText} = ${n(after)} kg`,
    category_kg_before: categoryKg, category_kg_after: categoryKg == null ? null : categoryKg + delta,
    total_kg_before: totalKg, total_kg_after: totalKg == null ? null : totalKg + delta,
  } as WhatIf;
}
