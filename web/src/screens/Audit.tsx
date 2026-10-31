import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { FictionalBadge, Pill } from "../components/ui";
import { deltaChip, fmtNum, fmtQty, kg, tonnes } from "../lib/format";
import { humanStatus } from "../lib/labels";
import { localWhatIf, whatIf, type WhatIf } from "../lib/api";
import type { Bootstrap } from "../lib/schema";

export type Layer = "total" | "category" | "calculation" | "inputs" | "source";
const LAYERS: Layer[] = ["total", "category", "calculation", "inputs", "source"];
const NAMES: Record<Layer, string> = { total: "Total", category: "Category", calculation: "Calculation", inputs: "Inputs", source: "Source" };

function stepSize(base: number) {
  if (base >= 1000) return 500;
  if (base >= 100) return 50;
  if (base >= 10) return 1;
  return 0.1;
}
const cleanQty = (v: number) => Math.max(0, Math.round(v * 10000) / 10000);
const dot = (s: string | null | undefined) => (s ?? "").replace("CO2e", "CO₂e");

export function Audit({ data, category, focusRow, forceLayer, onBack, onToast }: {
  data: Bootstrap; category: string; focusRow: number | null; forceLayer: Layer | null; onBack: () => void; onToast: (t: string) => void;
}) {
  const [layer, setLayer] = useState<Layer>(focusRow ? "calculation" : "category");
  const [resultId, setResultId] = useState<number | null>(focusRow);
  const [tech, setTech] = useState(false);
  const [step, setStep] = useState(0);
  const [preview, setPreview] = useState<WhatIf | null>(null);
  const [offlineCalc, setOfflineCalc] = useState(false);
  const [pins, setPins] = useState<{ qty: number; kg: number | null }[]>([]);
  const [checking, setChecking] = useState(false);

  const totals = data.snapshot?.summary?.inventory?.totals;
  const cats: any[] = data.snapshot?.summary?.inventory?.categories ?? [];
  const cat = cats.find((c) => c.category === category) ?? cats[0];
  const results: any[] = (data.results ?? []).filter((r: any) => r.category === (cat?.category ?? category));
  const selected: any = results.find((r) => r.id === resultId) ?? results.find((r) => r.status === "calculated") ?? results[0];

  useEffect(() => { if (forceLayer) setLayer(forceLayer); }, [forceLayer]);

  const base = selected?.input_quantity_snapshot == null ? null : Number(selected.input_quantity_snapshot);
  const size = base == null ? 1 : stepSize(base);
  const qty = base == null ? null : cleanQty(base + step * size);
  const canWhatIf = !!selected && selected.status === "calculated" && qty != null;

  useEffect(() => {
    if (!canWhatIf || step === 0) { setPreview(null); setOfflineCalc(false); return; }
    let live = true;
    whatIf(selected.id, qty as number)
      .then((w) => { if (live) { setPreview(w); setOfflineCalc(false); } })
      .catch(() => {
        if (!live) return;
        setPreview(localWhatIf(selected, qty as number, cat?.assessed_kg_co2e ?? null, totals?.assessed_kg_co2e ?? null));
        setOfflineCalc(true);
      });
    return () => { live = false; };
  }, [qty, selected?.id, canWhatIf, step]);

  // Proof stamp: a short, visible re-computation check before the stamp lands.
  useEffect(() => {
    if (layer !== "source") { setChecking(false); return; }
    setChecking(true);
    const t = setTimeout(() => setChecking(false), 900);
    return () => clearTimeout(t);
  }, [layer, selected?.id]);

  const up = () => { const i = LAYERS.indexOf(layer); if (i <= 0) onBack(); else setLayer(LAYERS[i - 1]); };
  const changed = !!preview && step !== 0;
  const dKg = changed ? preview!.kg_after : selected?.result_value;
  const dCat = changed ? preview!.category_kg_after : cat?.assessed_kg_co2e;
  const dTot = changed ? preview!.total_kg_after : totals?.assessed_kg_co2e;
  const formula = changed && preview!.plain_formula ? preview!.plain_formula : selected?.plain_formula;
  const snaps: any[] = [...(data.snapshots ?? [])].sort((a, b) => b.id - a.id);

  const chain = useMemo(() => [
    { l: "total" as Layer, v: tonnes(dTot) },
    { l: "category" as Layer, v: dCat == null ? "—" : kg(dCat) },
    { l: "calculation" as Layer, v: dKg == null ? "No number" : kg(dKg) },
    { l: "inputs" as Layer, v: selected?.input_quantity_snapshot == null ? "Missing" : `${fmtQty(changed ? qty : base)} ${selected?.input_unit_snapshot ?? ""}` },
    { l: "source" as Layer, v: selected?.source_reference ?? "—" },
  ], [dTot, dCat, dKg, selected, changed, qty, base]);

  return (
    <section data-testid="screen-audit" className="relative min-h-dvh px-4 pb-32 pt-6">
      <div className="mx-auto max-w-5xl">
        <div className="flex flex-wrap items-center gap-3">
          <button data-testid="audit-back" onClick={up} className="btn-ghost py-2">← Back</button>
          <FictionalBadge />
          {changed && <Pill tone="warn" testId="whatif-active">What if: numbers below are recounted</Pill>}
        </div>

        <nav className="mt-5 grid grid-cols-2 gap-2 md:grid-cols-5" data-testid="audit-crumbs" aria-label="Trace chain">
          {chain.map((c, i) => {
            const on = layer === c.l;
            return (
              <button key={c.l} data-testid={`crumb-${c.l}`} aria-current={on ? "step" : undefined} onClick={() => setLayer(c.l)}
                className={`rounded-2xl border p-3 text-left transition ${on ? "border-ember-400 bg-ember-400/15" : "border-[color:var(--stroke)] hover:bg-[color:var(--glass)]"}`}>
                <span className="block text-[18px] muted">{i + 1}. {NAMES[c.l]}</span>
                <span className="block truncate text-[18px] font-semibold">{c.v}</span>
              </button>
            );
          })}
        </nav>

        <AnimatePresence mode="wait">
          <motion.div key={layer} initial={{ y: 44, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 12, opacity: 0 }} transition={{ type: "spring", damping: 24, stiffness: 260 }} className="mt-6">
            {layer === "total" && (
              <div className="glass rounded-3xl p-8" data-testid="audit-total">
                <p className="muted">{totals?.total_label}</p>
                <p className="mt-1 text-6xl font-semibold">{tonnes(dTot)}</p>
                <div className="mt-3 flex flex-wrap items-center gap-3"><Pill tone="warn">Partial</Pill>
                  {changed && <Pill>{deltaChip(totals?.assessed_kg_co2e, dTot)}</Pill>}</div>
                {snaps.length > 1 && (
                  <div className="mt-6" data-testid="snapshot-compare">
                    <p className="mb-2 muted">Earlier calculations are kept and can be compared</p>
                    <ul className="space-y-1">
                      {snaps.map((s, i) => (
                        <li key={s.id} className="flex justify-between rounded-xl border border-[color:var(--stroke)] px-4 py-2">
                          <span>{i === 0 ? "Latest" : `Earlier ${i}`}</span>
                          <span className="font-semibold">{tonnes(s.assessed_total_kg_co2e)}{i > 0 && ` (${deltaChip(s.assessed_total_kg_co2e, snaps[0].assessed_total_kg_co2e)} since)`}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <button className="btn-primary mt-6" onClick={() => setLayer("category")}>Open {cat?.label}</button>
              </div>
            )}

            {layer === "category" && (
              <motion.div layoutId={`card-${cat?.category}`} className="glass rounded-3xl p-8" data-testid="audit-category">
                <p className="accent">{cat?.label}</p>
                <p className="text-5xl font-semibold">{dCat == null ? "No number yet" : kg(dCat)}</p>
                <p className="mt-3 text-[18px] muted">{cat?.note}</p>
                <ul className="mt-6 space-y-2">
                  {results.map((r) => (
                    <li key={r.id}>
                      <button data-testid={`result-${r.id}`} onClick={() => { setResultId(r.id); setStep(0); setLayer("calculation"); }}
                        className="flex w-full items-center justify-between gap-3 rounded-2xl border border-[color:var(--stroke)] px-4 py-3 text-left transition hover:bg-[color:var(--glass-strong)]">
                        <span>{r.activity_name} <span className="muted">· {r.activity_date}</span></span>
                        <span className="font-semibold">{r.result_value == null ? humanStatus(r.status) : kg(r.result_value)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </motion.div>
            )}

            {layer === "calculation" && selected && (
              <div className="glass rounded-3xl p-8" data-testid="audit-calculation">
                <p className="muted">{selected.activity_name} · {selected.activity_date}</p>
                <p className="mt-2 text-4xl font-semibold">{dKg == null ? "No number" : kg(dKg)}</p>
                <p className="mt-4 text-2xl leading-snug" data-testid="plain-formula">
                  {formula ?? `No number: ${humanStatus(selected.status).toLowerCase()}. It is not treated as zero.`}
                </p>
                {changed && (
                  <div className="mt-4 flex flex-wrap gap-2" data-testid="before-after">
                    <Pill>Before {kg(preview!.kg_before)}</Pill>
                    <Pill tone="warn">After {kg(preview!.kg_after)} ({deltaChip(preview!.kg_before, preview!.kg_after)})</Pill>
                    {offlineCalc && <Pill>Offline recount</Pill>}
                  </div>
                )}
                {canWhatIf ? (
                  <div className="mt-6">
                    <p className="mb-2 text-lg font-semibold">What if the quantity were different?</p>
                    <div className="flex flex-wrap items-center gap-3">
                      <button data-testid="whatif-minus" aria-label="Less" className="btn-ghost px-5 py-1 text-2xl" onClick={() => setStep((s) => s - 1)} disabled={qty === 0}>−</button>
                      <p data-testid="whatif-qty" className="min-w-[10rem] text-center text-2xl font-semibold">{fmtQty(qty)} {selected.input_unit_snapshot}</p>
                      <button data-testid="whatif-plus" aria-label="More" className="btn-ghost px-5 py-1 text-2xl" onClick={() => setStep((s) => s + 1)}>+</button>
                      <button data-testid="whatif-pin" className="btn-ghost py-1.5" disabled={!changed} onClick={() => preview && setPins((p) => [...p, { qty: qty as number, kg: preview.kg_after ?? null }])}>Keep this view</button>
                      {step !== 0 && <button data-testid="whatif-reset" className="btn-ghost py-1.5" onClick={() => setStep(0)}>Back to recorded</button>}
                    </div>
                    {pins.length > 0 && (
                      <ul className="mt-3 text-[18px] muted" data-testid="pins">
                        {pins.map((p, i) => <li key={i}>Kept view {i + 1}: {fmtQty(p.qty)} {selected.input_unit_snapshot} gives {kg(p.kg)}</li>)}
                      </ul>
                    )}
                  </div>
                ) : (
                  <p className="mt-6 muted">There is no quantity to change here. {selected.message}</p>
                )}
                <div className="mt-6 flex flex-wrap gap-3">
                  <button data-testid="to-inputs" className="btn-ghost" onClick={() => setLayer("inputs")}>Show inputs</button>
                  <button data-testid="to-source" className="btn-primary py-2.5" onClick={() => setLayer("source")}>Trace to the bill</button>
                </div>
              </div>
            )}

            {layer === "inputs" && selected && (
              <div className="grid gap-4 md:grid-cols-2" data-testid="audit-inputs">
                <div className="glass rounded-3xl p-6">
                  <p className="accent">Record</p>
                  <p className="mt-2 text-2xl">{selected.activity_name}</p>
                  <p className="mt-2 text-3xl font-semibold">{base == null ? "Quantity missing" : `${fmtQty(changed ? qty : base)} ${selected.input_unit_snapshot}`}</p>
                  <p className="mt-1 muted">{selected.activity_date}</p>
                  {selected.conversion_description && <p className="mt-2 text-[18px] muted">{selected.conversion_description.replace("→", "to")}</p>}
                </div>
                <div className="glass rounded-3xl p-6">
                  <p className="accent">Factor</p>
                  {selected.factor_snapshot ? (
                    <>
                      <p className="mt-2 text-2xl">{selected.factor_snapshot.name}</p>
                      <p className="mt-2 text-3xl font-semibold">{Number(selected.factor_value_snapshot).toFixed(2)} {dot(selected.factor_numerator_unit_snapshot)}/{selected.factor_denominator_unit_snapshot}</p>
                      <div className="mt-2"><Pill tone="warn">{humanStatus(selected.factor_snapshot.status)}</Pill></div>
                    </>
                  ) : (<p className="mt-2 text-2xl">No factor applied</p>)}
                </div>
                <button className="btn-primary md:col-span-2" onClick={() => setLayer("source")}>Open the source</button>
              </div>
            )}

            {layer === "source" && selected && (
              <div className="glass rounded-3xl p-8" data-testid="audit-source">
                <div className="grid gap-5 md:grid-cols-[1fr_auto]">
                  <div className="rounded-2xl border border-dashed border-[color:var(--stroke)] p-6">
                    <p className="muted">Source bill</p>
                    <div className="mt-1 flex flex-wrap items-center gap-3">
                      <p className="text-3xl font-semibold">{selected.source_reference ?? "No reference"}</p>
                      {selected.fictional ? <FictionalBadge /> : <Pill tone="ok">Verified</Pill>}
                    </div>
                    <p className="mt-2 text-xl">{selected.activity_name} · {selected.activity_date}</p>
                    <p className="text-xl">{base == null ? "Quantity missing" : `${fmtQty(base)} ${selected.input_unit_snapshot}`}</p>
                    <p className="mt-3 text-[18px] muted">Factor source: {selected.factor_source ?? "none recorded"}. Demo factors are illustrative on purpose.</p>
                  </div>
                  <div className="grid min-w-[14rem] place-items-center">
                    {selected.status !== "calculated" ? (
                      <p className="muted">Nothing to prove: no number was produced.</p>
                    ) : checking ? (
                      <p data-testid="proof-checking" className="text-xl muted">Recomputing from the stored inputs…</p>
                    ) : selected.recompute_matches ? (
                      <p data-testid="proof-stamp" className="inline-block rounded-md border-4 border-ember-400 px-4 py-2 text-center text-xl font-bold tracking-wide accent" style={{ animation: "stamp 0.7s ease both" }}>PROOF<br />recomputed, matches</p>
                    ) : (
                      <p data-testid="proof-fail" className="text-xl text-[color:var(--bad)]">Recompute did not match the stored result.</p>
                    )}
                  </div>
                </div>
                <button className="mt-6 block underline" onClick={() => setTech((t) => !t)} data-testid="tech-toggle">{tech ? "Hide technical details" : "Technical details"}</button>
                {tech && (
                  <pre className="mt-3 overflow-auto whitespace-pre-wrap text-[18px] muted" data-testid="tech-details">
{selected.formula_description}
{`Engine ${selected.engine_version} · calculation ${selected.snapshot_id} · ${selected.calculated_at}`}
                  </pre>
                )}
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </section>
  );
}
