import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { FictionalBadge } from "../components/ui";
import { kg, tonnes } from "../lib/format";
import type { Bootstrap } from "../lib/schema";

const STAGES = [
  { id: "bills", node: "Bills", title: "Start with the bill.", body: "Quantities come from source documents. If a quantity is missing, it stays missing." },
  { id: "factors", node: "Factors", title: "Attach a factor.", body: "Every factor carries a status. These demo factors are illustrative, not published values." },
  { id: "formula", node: "Formula", title: "Apply one formula.", body: "Emissions = quantity × factor. Only documented unit conversions are applied, and each one is written down." },
  { id: "total", node: "Total", title: "Read the total.", body: "Only calculated rows enter the total. It is labelled Partial until every declared category is assessed." },
  { id: "back", node: "Trace", title: "Now trace it back.", body: "The same chain runs in reverse: total, category, calculation, inputs, source bill." },
] as const;

export function Story({ data, onMill }: { data: Bootstrap; onMill: () => void }) {
  const outer = useRef<HTMLDivElement>(null);
  const [u, setU] = useState(0);

  // Progress is read from the element's live position, so it never goes stale during transitions.
  useEffect(() => {
    const read = () => {
      const el = outer.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const span = r.height - window.innerHeight;
      const v = span > 0 ? -r.top / span : 0;
      setU(Math.min(STAGES.length - 0.001, Math.max(0, v * STAGES.length)));
    };
    read();
    window.addEventListener("scroll", read, { passive: true });
    window.addEventListener("resize", read);
    const t = setInterval(read, 200);
    return () => { window.removeEventListener("scroll", read); window.removeEventListener("resize", read); clearInterval(t); };
  }, []);

  const stage = Math.floor(u);
  const reverse = stage === STAGES.length - 1;
  const s = STAGES[stage];
  const r = (data.results ?? []).find((x: any) => x.category === "purchased_electricity" && x.status === "calculated");
  const total = data.snapshot?.summary?.inventory?.totals?.assessed_kg_co2e;
  const cat = (data.snapshot?.summary?.inventory?.categories ?? []).find((c: any) => c.category === "purchased_electricity");
  const factor = r?.factor_snapshot;

  const visual: Record<string, { big: string; small: string }> = {
    bills: { big: r ? `${Number(r.input_quantity_snapshot).toLocaleString("en-IN")} ${r.input_unit_snapshot}` : "—", small: r ? `${r.activity_name} · ${r.source_reference}` : "" },
    factors: { big: r ? `${Number(r.factor_value_snapshot).toFixed(2)} ${r.factor_numerator_unit_snapshot}/${r.factor_denominator_unit_snapshot}`.replace("CO2e", "CO₂e") : "—", small: factor ? `${factor.name} · Illustrative` : "" },
    formula: { big: r?.plain_formula ?? "—", small: "quantity × factor, units checked" },
    total: { big: tonnes(total), small: "Partial · unresolved rows are omitted, not zeroed" },
    back: { big: r ? `${tonnes(total)} ← ${kg(cat?.assessed_kg_co2e)} ← ${kg(r.result_value)}` : "—", small: r ? `← ${Number(r.input_quantity_snapshot).toLocaleString("en-IN")} ${r.input_unit_snapshot} ← ${r.source_reference}` : "" },
  };

  return (
    <section data-testid="screen-story">
      <div ref={outer} className="relative" style={{ height: `${STAGES.length * 100 + 20}dvh` }}>
        <div className="sticky top-0 flex h-dvh flex-col px-4 pb-28 pt-6">
          <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-4">
            <FictionalBadge />
            <button data-testid="see-mill" onClick={onMill} className="btn-primary py-2">See the mill</button>
          </div>
          <div className="mx-auto mt-6 grid w-full max-w-5xl flex-1 items-center gap-8 md:grid-cols-[240px_1fr]">
            <ol className="relative space-y-6" aria-label="Chain">
              <span aria-hidden className="absolute left-[15px] top-4 h-[calc(100%-2rem)] w-0.5 bg-[color:var(--stroke)]" />
              <motion.span aria-hidden className="absolute left-[15px] top-4 w-0.5 origin-top bg-ember-400" animate={{ height: `calc(${Math.min(stage, 3) / 3} * (100% - 2rem))` }} transition={{ type: "spring", damping: 24, stiffness: 160 }} />
              {reverse && (
                <span aria-hidden className="absolute left-[14px] top-4 h-[calc(100%-2rem)] w-1" style={{ background: "repeating-linear-gradient(to top, var(--accent) 0 12px, transparent 12px 24px)", animation: "flow-up 0.9s linear infinite", backgroundSize: "100% 24px" }} />
              )}
              {STAGES.slice(0, 4).map((n, i) => {
                const lit = reverse || i <= stage;
                return (
                  <li key={n.id} data-testid={`story-node-${i}`} className="relative flex items-center gap-4">
                    <span className={`relative z-10 grid h-8 w-8 place-items-center rounded-full border-2 text-[18px] ${lit ? "border-ember-400 bg-ember-400 text-ink-950" : "border-[color:var(--stroke)]"}`} style={i === stage && !reverse ? { animation: "pulse-ring 1.4s ease-out infinite" } : undefined}>{i + 1}</span>
                    <span className={`text-xl ${lit ? "font-semibold" : "muted"}`}>{n.node}</span>
                  </li>
                );
              })}
            </ol>
            <div data-testid="story-caption" aria-live="polite">
              <AnimatePresence mode="wait">
                <motion.div key={stage} initial={{ opacity: 0, x: reverse ? -40 : 40 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.28 }} className="glass rounded-3xl p-8">
                  <p className="accent">{reverse ? "Reverse pass" : `Step ${stage + 1} of 4`}</p>
                  <p className="mt-2 text-4xl font-semibold">{s.title}</p>
                  <p className="mt-3 text-2xl leading-snug">{s.body}</p>
                  <div className="mt-6 rounded-2xl border border-[color:var(--stroke)] p-5">
                    <p className="text-3xl font-semibold">{visual[s.id].big}</p>
                    <p className="mt-1 text-[18px] muted">{visual[s.id].small}</p>
                  </div>
                </motion.div>
              </AnimatePresence>
              <p className="mt-4 text-[18px] muted">{reverse ? "Open the mill and click any number." : "Keep scrolling."}</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
