import { useMemo, useRef, useState } from "react";
import { motion, useMotionValue, useSpring, useTransform } from "framer-motion";
import { Line, LineChart } from "recharts";
import { FictionalBadge, Pill, Sheet } from "../components/ui";
import { humanStatus } from "../lib/labels";
import { kg, tonnes } from "../lib/format";
import { closeGap } from "../lib/api";
import type { Bootstrap } from "../lib/schema";

const GAP_HELP: Record<string, string> = {
  missing_factor: "There is no emission factor for this fuel in the library, so no number is shown. A sourced, attested factor closes this gap.",
  not_assessed: "This prototype has no method for it yet. It is listed, never guessed and never zero.",
  missing_activity_data: "The quantity has not been recorded yet, so nothing can be calculated. It is not treated as zero.",
};

function TiltCard({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const px = useMotionValue(0.5);
  const py = useMotionValue(0.5);
  const rx = useSpring(useTransform(py, [0, 1], [7, -7]), { stiffness: 220, damping: 20 });
  const ry = useSpring(useTransform(px, [0, 1], [-7, 7]), { stiffness: 220, damping: 20 });
  return (
    <motion.div
      ref={ref}
      style={{ rotateX: rx, rotateY: ry, transformPerspective: 900 }}
      whileHover={{ y: -8, scale: 1.02 }}
      onPointerMove={(e) => {
        const b = ref.current?.getBoundingClientRect();
        if (!b) return;
        px.set((e.clientX - b.left) / b.width);
        py.set((e.clientY - b.top) / b.height);
      }}
      onPointerLeave={() => { px.set(0.5); py.set(0.5); }}
      className="h-full"
    >
      {children}
    </motion.div>
  );
}

export function Mill({ data, offline, onData, onGapClosed, onToast, onOpenCategory }: {
  data: Bootstrap; offline: boolean; onData: (b: Bootstrap) => void; onGapClosed: () => void; onToast: (t: string) => void;
  onOpenCategory: (category: string, rowId?: number) => void;
}) {
  const [all, setAll] = useState(false);
  const [gap, setGap] = useState<any | null>(null);
  const [busy, setBusy] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const inv = data.snapshot?.summary?.inventory;
  const cats: any[] = inv?.categories ?? [];
  const totals = inv?.totals;
  const cards = cats.filter((c) => c.n_records > 0);
  const gaps = (data.results ?? []).filter((r: any) => r.status !== "calculated");

  const sparks = useMemo(() => {
    const map: Record<string, { v: number }[]> = {};
    const rows = [...(data.results ?? [])].sort((a: any, b: any) => String(a.activity_date).localeCompare(String(b.activity_date)));
    for (const r of rows) {
      if (r.result_value == null) continue;
      (map[r.category] ??= []).push({ v: r.result_value });
    }
    return map;
  }, [data.results]);

  async function fixGap() {
    setBusy(true);
    try {
      const before = totals?.assessed_kg_co2e;
      const next = await closeGap();
      onData(next);
      setGap(null);
      if (next.gap_closed) {
        onGapClosed();
        const after = next.snapshot?.summary?.inventory?.totals?.assessed_kg_co2e;
        onToast(`Gap closed. Total moved from ${tonnes(before)} to ${tonnes(after)}. The old calculation is kept.`);
      } else {
        onToast("Nothing to close: that factor is already in place.");
      }
    } catch {
      onToast("Closing a gap needs the live API.");
    } finally {
      setBusy(false);
    }
  }

  const canFix = (g: any) => g.status === "missing_factor" && g.category === "other_fossil_fuels";

  return (
    <section data-testid="screen-mill" className="min-h-dvh px-4 pb-32 pt-8">
      <div className="mx-auto max-w-6xl">
        <FictionalBadge />
        <div className="mt-6 flex flex-wrap items-end gap-4" data-testid="mill-hero">
          <div>
            <p className="text-[18px] muted">{totals?.total_label ?? "Partial assessed total"}</p>
            <p data-testid="mill-total" className="text-6xl font-semibold leading-none">{tonnes(totals?.assessed_kg_co2e)}</p>
          </div>
          <Pill tone="warn" testId="partial-pill">Partial</Pill>
        </div>
        <p className="mt-4 max-w-2xl text-[18px] muted">{kg(totals?.assessed_kg_co2e)} assessed. Unresolved rows are left out, never counted as zero.</p>

        <div className="relative mt-10">
          <div ref={scroller} data-testid="category-carousel" className="flex snap-x snap-mandatory gap-5 overflow-x-auto pb-4 pt-2 no-scrollbar">
            {cards.map((c) => {
              const numeric = c.assessed_kg_co2e != null;
              const series = sparks[c.category];
              return (
                <motion.div key={c.category} layoutId={`card-${c.category}`} className="w-[300px] shrink-0 snap-start">
                  <TiltCard>
                    <button data-testid={`cat-${c.category}`} onClick={() => onOpenCategory(c.category)} className={`glass h-full w-full rounded-3xl p-5 text-left ${numeric ? "" : "border-dashed"}`}>
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-xl font-semibold">{c.label}</p>
                        <Pill tone={c.completeness === "all_records_calculated" ? "ok" : "warn"}>{humanStatus(c.completeness)}</Pill>
                      </div>
                      <p className="mt-4 text-3xl font-semibold">{numeric ? kg(c.assessed_kg_co2e) : "No number yet"}</p>
                      <div className="mt-3 h-14">
                        {series && series.length > 1 ? (
                          <LineChart width={250} height={56} data={series}>
                            <Line type="monotone" dataKey="v" stroke="#e8a15a" strokeWidth={2.5} dot={{ r: 3, fill: "#e8a15a" }} isAnimationActive={false} />
                          </LineChart>
                        ) : (
                          <p className="text-[18px] muted">{numeric ? "One record" : "Gap, not zero"}</p>
                        )}
                      </div>
                    </button>
                  </TiltCard>
                </motion.div>
              );
            })}
          </div>
          <div className="mt-2 flex gap-2">
            <button aria-label="Scroll categories left" className="btn-ghost py-1" onClick={() => scroller.current?.scrollBy({ left: -320, behavior: "smooth" })}>←</button>
            <button aria-label="Scroll categories right" className="btn-ghost py-1" onClick={() => scroller.current?.scrollBy({ left: 320, behavior: "smooth" })}>→</button>
          </div>
        </div>

        <div className="mt-8" data-testid="gap-chips">
          <p className="mb-3 text-[18px] muted">{gaps.length} gaps. Click one to see what closes it.</p>
          <div className="flex flex-wrap items-center gap-3">
            {gaps.slice(0, 3).map((g: any) => (
              <button key={g.id} data-testid={`gap-${g.category}`} onClick={() => setGap(g)} className="glass rounded-full px-4 py-2">
                {g.category_label}: {humanStatus(g.status)}
              </button>
            ))}
            <button data-testid="see-all-gaps" onClick={() => setAll(true)} className="btn-ghost py-2">See all</button>
          </div>
        </div>
      </div>

      <Sheet open={all} title="Every category" onClose={() => setAll(false)} testId="sheet-all">
        <ul className="space-y-3">
          {cats.map((c) => (
            <li key={c.category} className="flex items-start justify-between gap-3 border-b border-[color:var(--stroke)] pb-3">
              <div>
                <p className="font-medium">{c.label}</p>
                <p className="text-[18px] muted">{c.note}</p>
              </div>
              <Pill>{humanStatus(c.completeness)}</Pill>
            </li>
          ))}
        </ul>
        <p className="mt-4 text-[18px] muted">Categories with no records are not assessed. That is not zero.</p>
      </Sheet>

      <Sheet open={!!gap} title={gap ? `${gap.category_label}: ${humanStatus(gap.status)}` : ""} onClose={() => setGap(null)} testId="sheet-gap">
        {gap && (
          <div>
            <p className="text-2xl">{GAP_HELP[gap.status] ?? gap.message}</p>
            <p className="mt-3 text-[18px] muted">{gap.activity_name}</p>
            <div className="mt-6 flex flex-wrap gap-3">
              <button data-testid="gap-trace" className="btn-ghost" onClick={() => { const g = gap; setGap(null); onOpenCategory(g.category, g.id); }}>Trace it</button>
              {canFix(gap) && (
                <button data-testid="close-gap" disabled={busy || offline} className="btn-primary" onClick={() => void fixGap()}>
                  {busy ? "Closing…" : "Add a fictional demo factor"}
                </button>
              )}
            </div>
            {canFix(gap) && <p className="mt-4 text-[18px] muted">{offline ? "Needs the live API." : "Demo only: a made-up, unsourced factor so you can watch a gap close. Real factors need a source."}</p>}
          </div>
        )}
      </Sheet>
    </section>
  );
}
