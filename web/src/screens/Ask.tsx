import { useState } from "react";
import { FictionalBadge } from "../components/ui";
import type { Pitch } from "../lib/schema";

const inr = (n: number) => `Rs ${n.toLocaleString("en-IN")}`;

export function Ask({ pitch }: { pitch: Pitch }) {
  const [note, setNote] = useState(true);
  const mismatch = pitch.showReconcileNote && pitch.pilotAmountInr !== pitch.previousDeckAmountInr;
  return (
    <section data-testid="screen-ask" className="min-h-dvh px-4 pb-32 pt-8">
      <div className="mx-auto max-w-6xl">
        <FictionalBadge />
        {mismatch && note && (
          <div data-testid="presenter-note" className="mt-4 flex items-start justify-between gap-4 rounded-2xl border border-ember-400/60 bg-ember-400/15 p-4">
            <p>Presenter check: the deck said {inr(pitch.previousDeckAmountInr)}; this screen says {inr(pitch.pilotAmountInr)}. {pitch.reconcileNote}</p>
            <button className="btn-ghost shrink-0 py-1" onClick={() => setNote(false)}>Dismiss</button>
          </div>
        )}
        <h1 className="mt-4 text-4xl font-semibold">The ask</h1>
        <div className="mt-8 grid gap-5 lg:grid-cols-3">
          <article className="glass rounded-3xl p-6">
            <p className="accent">Why a pilot, and what it unlocks</p>
            <p data-testid="pilot-amount" className="mt-3 text-5xl font-semibold">{inr(pitch.pilotAmountInr)}</p>
            <p className="mt-3">{pitch.whyPilot}</p>
            <ul className="mt-4 list-disc space-y-2 pl-5">{pitch.unlocks.map((u) => <li key={u}>{u}</li>)}</ul>
          </article>
          <article className="glass rounded-3xl p-6">
            <p className="accent" data-testid="timeline-days">{pitch.timelineDays} days</p>
            <ol className="mt-4 space-y-5 border-l-2 border-ember-400/60 pl-5">
              {pitch.timeline.map((t) => (<li key={t.days}><span className="text-2xl font-semibold">Days {t.days}</span><p className="mt-1">{t.label}</p></li>))}
            </ol>
          </article>
          <article className="glass rounded-3xl p-6">
            <p className="accent">Validated vs not</p>
            <p className="mt-4 text-xl font-semibold text-[color:var(--ok)]">Built and tested</p>
            <ul className="mt-2 list-disc space-y-1 pl-5">{pitch.validated.map((u) => <li key={u}>{u}</li>)}</ul>
            <p className="mt-4 text-xl font-semibold text-[color:var(--bad)]">Not claimed</p>
            <ul className="mt-2 list-disc space-y-1 pl-5">{pitch.notValidated.map((u) => <li key={u}>{u}</li>)}</ul>
          </article>
        </div>
      </div>
    </section>
  );
}
