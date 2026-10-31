import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { FictionalBadge, Drawer, Pill } from "../components/ui";
import { humanStatus, plainError } from "../lib/labels";
import { commitImportFile, previewImportFile } from "../lib/api";
import type { Bootstrap } from "../lib/schema";

type Row = { row_number: number; status: string; errors: string[]; raw: Record<string, string> };
const FIELD: Record<string, string> = { purchased_electricity: "kWh", diesel: "L" };

export function DataRoom({ data, offline, onData, onGapClosed, onToast, onReset, scanSignal = 0 }: {
  data: Bootstrap; offline: boolean; onData: (b: Bootstrap) => void; onGapClosed: () => void; onToast: (t: string) => void; onReset: () => void; scanSignal?: number;
}) {
  const [drawer, setDrawer] = useState(false);
  const [rows, setRows] = useState<Row[] | null>(null);
  const [shown, setShown] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const [scanning, setScanning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [counts, setCounts] = useState<{ valid: number; bad: number } | null>(null);
  const [committed, setCommitted] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  function reveal(list: Row[]) {
    if (timer.current) clearInterval(timer.current);
    setRows(list); setShown(0); setScanning(true);
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    let n = 0;
    timer.current = setInterval(() => {
      n += reduce ? list.length : 1;
      setShown(Math.min(n, list.length));
      if (n >= list.length) { if (timer.current) clearInterval(timer.current); setScanning(false); }
    }, 170);
  }
  useEffect(() => () => { if (timer.current) clearInterval(timer.current); }, []);

  async function scan(f: File, kind?: "ok" | "err") {
    setFile(f); setCommitted(false); setCounts(null);
    let pv: any = null;
    try { pv = await previewImportFile(f); }
    catch { if (kind && data.sample_previews?.[kind]) pv = data.sample_previews[kind]; }
    if (!pv) { onToast("Could not read that file right now."); return; }
    if (pv.header_errors?.length) { onToast(plainError(pv.header_errors[0])); return; }
    setCounts({ valid: pv.n_valid ?? 0, bad: pv.n_rejected ?? 0 });
    reveal((pv.rows as Row[]) ?? []);
  }

  async function useBundled(kind: "ok" | "err") {
    const text = kind === "ok" ? data.sample_csv : data.sample_csv_with_errors;
    if (!text) return;
    await scan(new File([text], kind === "ok" ? "demo_activities.csv" : "demo_activities_with_errors.csv", { type: "text/csv" }), kind);
  }

  const lastScan = useRef(0);
  useEffect(() => {
    if (scanSignal && scanSignal !== lastScan.current) { lastScan.current = scanSignal; void useBundled("err"); }
  }, [scanSignal]);

  async function commit() {
    if (!file) return;
    setBusy(true);
    try {
      const next = await commitImportFile(file);
      onData(next);
      if (next.gap_closed) onGapClosed();
      setCommitted(true);
      onToast(`Added ${next.import_result?.imported ?? 0} rows. A new calculation was stored; the old one is kept.`);
    } catch { onToast("Not added. Nothing was written."); }
    finally { setBusy(false); }
  }

  const done = rows != null && shown >= rows.length;
  return (
    <section data-testid="screen-data" className="min-h-dvh px-4 pb-32 pt-8">
      <div className="mx-auto max-w-4xl">
        <FictionalBadge />
        <div className="mt-6 flex items-end justify-between gap-4">
          <h1 className="text-4xl font-semibold">Data room</h1>
          <button data-testid="open-records" onClick={() => setDrawer(true)} className="btn-ghost">Records ({(data.activities ?? []).length})</button>
        </div>
        <label data-testid="drop-zone"
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files?.[0]; if (f) void scan(f); }}
          className={`glass relative mt-8 block cursor-pointer overflow-hidden rounded-3xl border-2 border-dashed p-10 text-center transition ${drag ? "border-ember-400 bg-ember-400/10" : ""}`}>
          <input type="file" accept=".csv" className="hidden" data-testid="file-input" onChange={(e) => { const f = e.target.files?.[0]; if (f) void scan(f); }} />
          {scanning && <span className="pointer-events-none absolute inset-x-0 top-0 h-1 bg-ember-400" style={{ animation: "scan 1.1s linear infinite" }} />}
          <p className="text-2xl">Drop a CSV here, or click to choose one</p>
          <p className="mt-2 muted">Checked first. Nothing is saved until you confirm.</p>
        </label>
        <div className="mt-4 flex flex-wrap gap-3">
          <button data-testid="sample-err" className="btn-primary py-2.5" onClick={() => void useBundled("err")}>Scan a file with mistakes</button>
          <button data-testid="sample-ok" className="btn-ghost" onClick={() => void useBundled("ok")}>Re-upload the seeded bills</button>
          <button data-testid="reset-demo" className="btn-ghost" onClick={onReset}>Reset demo</button>
        </div>

        {counts && done && (
          <p className="mt-5 text-2xl" data-testid="import-summary">
            <span className="text-[color:var(--ok)]">{counts.valid} accepted</span>, <span className="text-[color:var(--bad)]">{counts.bad} rejected</span>. Nothing is dropped silently.
          </p>
        )}
        {rows && (
          <ul className="mt-4 max-h-[44vh] space-y-2 overflow-auto" data-testid="csv-rows">
            {rows.slice(0, shown).map((r) => {
              const ok = r.status === "valid";
              const name = r.raw?.activity_name || "Row";
              return (
                <motion.li key={r.row_number} initial={{ opacity: 0, x: -16 }} animate={{ opacity: 1, x: 0 }} data-testid={`csv-row-${r.row_number}`} data-status={ok ? "valid" : "rejected"}
                  className={`rounded-2xl border px-4 py-3 ${ok ? "border-emerald-400/50 bg-emerald-500/15" : "border-rose-400/50 bg-rose-500/10"}`}>
                  <span className="font-semibold">Line {r.row_number}</span>
                  <span className="muted"> · {name}{r.raw?.quantity ? ` · ${r.raw.quantity} ${r.raw.unit ?? ""}` : ""}</span>
                  <span className={`ml-2 font-semibold ${ok ? "text-[color:var(--ok)]" : "text-[color:var(--bad)]"}`}>{ok ? "accepted" : "rejected"}</span>
                  {!ok && <span className="block">{r.errors.map(plainError).join(" ")}</span>}
                </motion.li>
              );
            })}
          </ul>
        )}
        {done && counts && counts.valid > 0 && !committed && (
          <button data-testid="commit-import" disabled={busy || offline} onClick={() => void commit()} className="btn-primary mt-6">
            {offline ? "Adding needs the live API" : busy ? "Adding…" : `Add the ${counts.valid} accepted rows`}
          </button>
        )}
        {committed && <p className="mt-6 text-xl accent" data-testid="committed">Added. The mill and every trace now include these rows.</p>}
      </div>
      <Drawer open={drawer} title="Activity records" onClose={() => setDrawer(false)} testId="records-drawer">
        <ul className="space-y-3">
          {(data.activities ?? []).map((a: any) => (
            <li key={a.id} className="border-b border-[color:var(--stroke)] pb-3">
              <p className="font-medium">{a.activity_name}</p>
              <p className="text-[18px] muted">{a.activity_date} · {a.quantity == null ? "quantity missing" : `${a.quantity} ${a.unit}`} · {a.source_reference}</p>
              <div className="mt-1 flex flex-wrap gap-2">
                <Pill>{humanStatus(a.status)}</Pill>
                {a.provenance === "synthetic_demo" && <FictionalBadge />}
              </div>
            </li>
          ))}
        </ul>
      </Drawer>
    </section>
  );
}
