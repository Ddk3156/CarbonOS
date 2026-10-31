import { motion } from "framer-motion";
import { CountUp, FictionalBadge, Pill } from "../components/ui";
import { kg, tonnes } from "../lib/format";
import type { Bootstrap } from "../lib/schema";

/** The proof in one line: total <- category <- calculation <- source bill, from the stored snapshot. */
export function ChainPreview({ data }: { data: Bootstrap }) {
  const r = (data.results ?? []).find((x: any) => x.category === "purchased_electricity" && x.status === "calculated");
  const cat = (data.snapshot?.summary?.inventory?.categories ?? []).find((c: any) => c.category === "purchased_electricity");
  const total = data.snapshot?.summary?.inventory?.totals?.assessed_kg_co2e;
  if (!r) return null;
  const nodes = [
    { k: "Total", v: tonnes(total) },
    { k: "Category", v: `${cat?.label ?? "Electricity"} · ${kg(cat?.assessed_kg_co2e)}` },
    { k: "Calculation", v: r.plain_formula as string },
    { k: "Source bill", v: r.source_reference as string },
  ];
  return (
    <ol data-testid="chain-preview" className="mx-auto mt-10 flex max-w-5xl flex-wrap items-stretch justify-center gap-2">
      {nodes.map((n, i) => (
        <motion.li key={n.k} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1.3 + i * 0.35, type: "spring", damping: 20 }} className="flex items-center gap-2">
          {i > 0 && <span aria-hidden className="accent text-2xl">←</span>}
          <span className="glass rounded-2xl px-4 py-2 text-left">
            <span className="block text-[18px] muted">{n.k}</span>
            <span className="block text-[18px] font-medium">{n.v}</span>
          </span>
        </motion.li>
      ))}
    </ol>
  );
}

export function Cover({ data, tonnes: t, onStart, onTour }: { data: Bootstrap; tonnes: number; onStart: () => void; onTour: () => void }) {
  return (
    <section data-testid="screen-cover" className="relative flex min-h-dvh flex-col items-center justify-center px-6 pb-12 text-center">
      <FictionalBadge className="absolute left-6 top-6" />
      <motion.p initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="mb-6 text-[18px] tracking-[0.28em] accent">CARBONOS SUGAR</motion.p>
      <div className="text-[clamp(3.4rem,12vw,8rem)] font-semibold leading-none tracking-tight">
        <CountUp value={t} digits={3} testId="cover-count" />
        <span className="ml-3 text-[clamp(1.1rem,2.4vw,2rem)] font-medium muted">t CO₂e</span>
      </div>
      <div className="mt-5 flex flex-wrap items-center justify-center gap-3"><Pill tone="warn">Partial · fictional demo mill</Pill></div>
      <p className="mt-8 max-w-2xl text-3xl font-medium">Every number, traceable to its bill.</p>
      <div className="mt-9 flex flex-wrap items-center justify-center gap-4">
        <button data-testid="start-audit" onClick={onStart} className="btn-primary">Start the audit</button>
        <button data-testid="start-tour" onClick={onTour} className="btn-ghost">Start demo · 90 s</button>
      </div>
      <ChainPreview data={data} />
      <p className="mt-8 max-w-xl text-[18px] muted">Missing data is never zero. Partial totals say so.</p>
    </section>
  );
}
