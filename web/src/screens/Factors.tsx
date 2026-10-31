import { useState } from "react";
import { FictionalBadge, Pill } from "../components/ui";
import { humanStatus } from "../lib/labels";
import type { Bootstrap } from "../lib/schema";

function Lock({ open }: { open: boolean }) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
      <rect x="5" y="11" width="14" height="10" rx="2" />
      <path d={open ? "M8 11V7a4 4 0 0 1 7.5-2" : "M8 11V7a4 4 0 0 1 8 0v4"} />
    </svg>
  );
}

export function Factors({ data }: { data: Bootstrap }) {
  const [flipped, setFlipped] = useState<string | null>(null);
  const factors: any[] = data.factors ?? [];
  const verified = factors.filter((f) => f.status === "verified_for_use").length;
  return (
    <section data-testid="screen-factors" className="min-h-dvh px-4 pb-32 pt-8">
      <div className="mx-auto max-w-5xl">
        <FictionalBadge />
        <h1 className="mt-6 text-4xl font-semibold">Factor vault</h1>
        <p className="mt-3 max-w-2xl text-xl muted">No real emission factors ship with this prototype. Tap a card to see its source, year and status.</p>
        <div className="mt-4"><Pill tone={verified ? "ok" : "warn"} testId="verified-count">{verified} of {factors.length} verified for real reporting</Pill></div>
        {factors.length === 0 && <p className="mt-8 muted">No factors yet.</p>}
        <div className="mt-8 grid gap-5 md:grid-cols-2">
          {factors.map((f) => {
            const open = flipped === f.id;
            const locked = f.status !== "verified_for_use";
            return (
              <button key={f.id} data-testid={`factor-${f.id}`} aria-pressed={open} onClick={() => setFlipped(open ? null : f.id)} className="h-60 text-left [perspective:1200px]">
                <div className={`relative h-full w-full transition-transform duration-500 [transform-style:preserve-3d] ${open ? "[transform:rotateY(180deg)]" : ""}`}>
                  <div className="glass absolute inset-0 rounded-3xl p-6 [backface-visibility:hidden]" style={{ background: "var(--bg)" }}>
                    <div className="flex items-start justify-between gap-3">
                      <p className="text-xl font-semibold">{f.name}</p>
                      <Pill tone={locked ? "warn" : "ok"}><span className="mr-1.5"><Lock open={!locked} /></span>{locked ? "Locked" : "Unlocked"}</Pill>
                    </div>
                    <p className="mt-6 text-4xl font-semibold">{Number(f.value).toFixed(2)} <span className="text-xl font-medium muted">{String(f.numerator_unit).replace("CO2e", "CO₂e")} per {f.denominator_unit}</span></p>
                    <p className="mt-4 muted">{humanStatus(f.status)}. Tap to flip.</p>
                  </div>
                  <div className="glass absolute inset-0 overflow-auto rounded-3xl p-6 [backface-visibility:hidden] [transform:rotateY(180deg)]" style={{ background: "var(--bg)" }}>
                    <p><span className="muted">Source: </span>{f.source_organization || f.source_document || "none recorded"}</p>
                    <p className="mt-1"><span className="muted">Year: </span>{f.applicable_year ?? "not stated"}</p>
                    <p className="mt-1"><span className="muted">Where: </span>{f.geography ?? "not stated"}</p>
                    <p className="mt-1"><span className="muted">Status: </span>{humanStatus(f.status)}</p>
                    <p className="mt-2 text-[18px] muted">{f.notes}</p>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}
