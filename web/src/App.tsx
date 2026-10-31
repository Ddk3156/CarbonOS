import { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { loadBootstrap, resetDemo } from "./lib/api";
import type { Bootstrap } from "./lib/schema";
import { Cover } from "./screens/Cover";
import { Story } from "./screens/Story";
import { Mill } from "./screens/Mill";
import { Audit, type Layer } from "./screens/Audit";
import { DataRoom } from "./screens/DataRoom";
import { Factors } from "./screens/Factors";
import { Report } from "./screens/Report";
import { Ask } from "./screens/Ask";
import { Dock, Palette, SCREEN_ORDER, ThemeToggle, Tour } from "./components/chrome";
import { Confetti, ScreenErrorBoundary, Skeleton, ToastHost } from "./components/ui";
import type { Screen } from "./appState";

const tourScale = Number(new URLSearchParams(window.location.search).get("tourScale") || 1) || 1;

export default function App() {
  const [data, setData] = useState<Bootstrap | null>(null);
  const [fromFallback, setFromFallback] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [screen, setScreen] = useState<Screen>("cover");
  const [category, setCategory] = useState("purchased_electricity");
  const [focusRow, setFocusRow] = useState<number | null>(null);
  const [auditLayer, setAuditLayer] = useState<Layer | null>(null);
  const [palette, setPalette] = useState(false);
  const [tour, setTour] = useState(false);
  const [toasts, setToasts] = useState<{ id: string; text: string }[]>([]);
  const [confetti, setConfetti] = useState(false);
  const [scanTick, setScanTick] = useState(0);

  const toast = useCallback((text: string) => setToasts((t) => [...t, { id: `${Date.now()}-${Math.random()}`, text }]), []);
  const dropToast = useCallback((id: string) => setToasts((t) => t.filter((x) => x.id !== id)), []);

  useEffect(() => {
    let live = true;
    loadBootstrap()
      .then(({ data: d, fromFallback: fb }) => {
        if (!live) return;
        setData(d);
        setFromFallback(fb);
        if (fb) toast("Offline: showing the bundled snapshot of the fictional demo.");
      })
      .catch((e: Error) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [toast]);

  const go = useCallback((s: Screen) => setScreen(s), []);
  const stopTour = useCallback(() => setTour(false), []);
  const openElec = useCallback(() => { setCategory("purchased_electricity"); setFocusRow(null); setScreen("audit"); }, []);
  const scan = useCallback(() => setScanTick((n) => n + 1), []);
  const celebrate = useCallback(() => { setConfetti(true); setTimeout(() => setConfetti(false), 2400); }, []);
  const reset = useCallback(async () => {
    try { setData(await resetDemo()); toast("Demo restored to its starting state."); }
    catch { toast("Reset needs the live API."); }
  }, [toast]);

  useEffect(() => { window.scrollTo(0, 0); }, [screen]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette((p) => !p); return; }
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      const el = e.target as HTMLElement | null;
      const typing = el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
      if (typing || palette || document.querySelector('[role="dialog"]')) return;
      const i = SCREEN_ORDER.indexOf(screen);
      setScreen(SCREEN_ORDER[e.key === "ArrowRight" ? Math.min(SCREEN_ORDER.length - 1, i + 1) : Math.max(0, i - 1)]);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [screen, palette]);

  const tonnes = useMemo(() => {
    const kg = data?.snapshot?.summary?.inventory?.totals?.assessed_kg_co2e;
    return kg == null ? 0 : kg / 1000;
  }, [data]);

  if (error) {
    return (
      <div className="flex min-h-dvh items-center justify-center p-8">
        <div className="glass max-w-lg rounded-3xl p-8">
          <p className="text-2xl font-semibold">The demo could not start</p>
          <p className="mt-3 muted">Run <code>npm run demo</code> from the project folder, then reload.</p>
        </div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="min-h-dvh p-8" data-testid="loading">
        <Skeleton className="mx-auto mt-32 h-40 max-w-xl" />
        <Skeleton className="mx-auto mt-6 h-12 max-w-sm" />
      </div>
    );
  }
  if (!data.ready) {
    return <div className="flex min-h-dvh items-center justify-center p-8"><div className="glass rounded-3xl p-8">No mill is loaded yet.</div></div>;
  }

  return (
    <div className="min-h-dvh">
      <ThemeToggle />
      {fromFallback && (
        <p data-testid="offline-pill" className="fixed left-1/2 top-5 z-40 -translate-x-1/2 rounded-full border border-ember-400/50 bg-ember-400/15 px-4 py-1 text-[18px]">
          Offline · bundled snapshot
        </p>
      )}
      <AnimatePresence mode="wait" initial={false}>
        <motion.div key={screen} initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.22, ease: "easeOut" }}>
          <ScreenErrorBoundary name={screen}>
            {screen === "cover" && <Cover data={data} tonnes={tonnes} onStart={() => setScreen("story")} onTour={() => { setTour(true); setScreen("cover"); }} />}
            {screen === "story" && <Story data={data} onMill={() => setScreen("mill")} />}
            {screen === "mill" && (
              <Mill data={data} offline={fromFallback} onData={setData} onGapClosed={celebrate} onToast={toast}
                onOpenCategory={(c, rowId) => { setCategory(c); setFocusRow(rowId ?? null); setScreen("audit"); }} />
            )}
            {screen === "audit" && (
              <Audit key={`${category}-${focusRow ?? "x"}`} data={data} category={category} focusRow={focusRow} forceLayer={auditLayer} onBack={() => setScreen("mill")} onToast={toast} />
            )}
            {screen === "data" && <DataRoom data={data} offline={fromFallback} onData={setData} onGapClosed={celebrate} onToast={toast} onReset={reset} scanSignal={scanTick} />}
            {screen === "factors" && <Factors data={data} />}
            {screen === "report" && <Report data={data} offline={fromFallback} />}
            {screen === "ask" && data.pitch && <Ask pitch={data.pitch} />}
          </ScreenErrorBoundary>
        </motion.div>
      </AnimatePresence>
      {screen !== "cover" && <Dock screen={screen} onGo={go} />}
      <Palette open={palette} onOpen={setPalette} onGo={go} onTour={() => { setPalette(false); setTour(true); }} onReset={() => { setPalette(false); void reset(); }} />
      <Tour running={tour} scale={tourScale} onGo={go} onStop={stopTour} onScan={scan} onOpenElectricity={openElec} onAuditLayer={setAuditLayer} />
      <ToastHost toasts={toasts} onDone={dropToast} />
      <Confetti show={confetti} />
    </div>
  );
}
