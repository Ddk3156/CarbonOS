import { Command } from "cmdk";
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { Screen } from "../appState";
import type { Layer } from "../screens/Audit";

const ITEMS: { id: Screen; label: string; icon: string }[] = [
  { id: "cover", label: "Cover", icon: "◎" },
  { id: "story", label: "Story", icon: "↕" },
  { id: "mill", label: "Mill", icon: "▣" },
  { id: "audit", label: "Trail", icon: "↳" },
  { id: "data", label: "Data", icon: "▤" },
  { id: "factors", label: "Factors", icon: "◇" },
  { id: "report", label: "Report", icon: "▢" },
  { id: "ask", label: "Ask", icon: "₹" },
];
export const SCREEN_ORDER: Screen[] = ITEMS.map((i) => i.id);

export function Dock({ screen, onGo }: { screen: Screen; onGo: (s: Screen) => void }) {
  return (
    <nav data-testid="dock" aria-label="Screens" className="glass fixed bottom-5 left-1/2 z-40 flex max-w-[96vw] -translate-x-1/2 gap-1 overflow-x-auto rounded-full px-2 py-2 shadow-glass no-scrollbar">
      {ITEMS.map((it) => (
        <button key={it.id} data-testid={`dock-${it.id}`} aria-current={screen === it.id ? "page" : undefined} onClick={() => onGo(it.id)}
          className={`whitespace-nowrap rounded-full px-3.5 py-2 text-[18px] transition active:scale-95 ${screen === it.id ? "bg-ember-400 font-semibold text-ink-950" : "hover:bg-[color:var(--glass-strong)]"}`}>
          <span className="mr-1.5" aria-hidden>{it.icon}</span>{it.label}
        </button>
      ))}
    </nav>
  );
}

export function Palette({ open, onOpen, onGo, onTour, onReset }: { open: boolean; onOpen: (v: boolean) => void; onGo: (s: Screen) => void; onTour: () => void; onReset: () => void }) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onOpen(false); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onOpen]);
  if (!open) return null;
  const item = "cursor-pointer rounded-xl px-3 py-2 data-[selected=true]:bg-ember-400/25";
  return (
    <div data-testid="command-palette">
      <button aria-label="Close palette" className="fixed inset-0 z-[75] bg-black/55" onClick={() => onOpen(false)} />
      <Command className="glass fixed left-1/2 top-[18%] z-[76] w-[min(520px,92vw)] -translate-x-1/2 rounded-3xl p-3" style={{ background: "var(--bg)" }} label="Jump to a screen">
        <Command.Input autoFocus placeholder="Jump to a screen or action…" className="w-full rounded-2xl bg-[color:var(--glass-strong)] px-4 py-3 outline-none" />
        <Command.List className="mt-2 max-h-80 overflow-auto">
          <Command.Empty className="px-3 py-2 muted">Nothing matches.</Command.Empty>
          {ITEMS.map((it) => (
            <Command.Item key={it.id} value={it.label} onSelect={() => { onGo(it.id); onOpen(false); }} className={item}>
              <span className="mr-2" aria-hidden>{it.icon}</span>{it.label}
            </Command.Item>
          ))}
          <Command.Item value="Start the guided demo" onSelect={onTour} className={item}>Start the guided demo</Command.Item>
          <Command.Item value="Reset the demo" onSelect={onReset} className={item}>Reset the demo</Command.Item>
        </Command.List>
      </Command>
    </div>
  );
}

export function ThemeToggle() {
  const [light, setLight] = useState(() => document.documentElement.classList.contains("light"));
  return (
    <button data-testid="theme-toggle" className="glass fixed right-5 top-5 z-40 rounded-full px-4 py-2 text-[18px] transition active:scale-95"
      onClick={() => {
        const next = !light;
        setLight(next);
        document.documentElement.classList.toggle("light", next);
        document.documentElement.classList.toggle("dark", !next);
        try { localStorage.setItem("carbonos-theme", next ? "light" : "dark"); } catch { /* storage may be blocked */ }
      }}>
      {light ? "Dark" : "Light"}
    </button>
  );
}

type Step = { title: string; body: string; screen: Screen; ms: number };
// Sums to 90 s.
const TOUR: Step[] = [
  { screen: "cover", title: "One number", body: "A partial total from fictional bills. It is not the mill’s complete footprint.", ms: 9000 },
  { screen: "story", title: "The chain", body: "Bills, factors, one formula, a labelled partial total, then the same chain in reverse.", ms: 11000 },
  { screen: "mill", title: "The mill", body: "Open a category. Gaps stay visible as chips and are never shown as zero.", ms: 11000 },
  { screen: "audit", title: "Reverse trace", body: "Total, category, calculation, inputs, source. The stamp appears when the engine recomputes the stored result.", ms: 24000 },
  { screen: "data", title: "Data room", body: "Valid rows turn green. Rejected rows keep their errors. Nothing is dropped silently.", ms: 12000 },
  { screen: "factors", title: "Factor vault", body: "These factors stay locked: illustrative, not verified for use.", ms: 8000 },
  { screen: "report", title: "Certificate", body: "Exports come from the stored snapshot, limitations included.", ms: 7000 },
  { screen: "ask", title: "The ask", body: "Rs 60,000 and 45 days, from an editable config file.", ms: 8000 },
];

export function Tour({ running, scale = 1, onGo, onStop, onScan, onOpenElectricity, onAuditLayer }: {
  running: boolean; scale?: number; onGo: (s: Screen) => void; onStop: () => void; onScan: () => void; onOpenElectricity: () => void; onAuditLayer: (l: Layer | null) => void;
}) {
  const [i, setI] = useState(0);
  const cb = useRef({ onGo, onStop, onScan, onOpenElectricity, onAuditLayer });
  cb.current = { onGo, onStop, onScan, onOpenElectricity, onAuditLayer };

  useEffect(() => {
    if (!running) { setI(0); cb.current.onAuditLayer(null); return; }
    const step = TOUR[i];
    const timers: ReturnType<typeof setTimeout>[] = [];
    cb.current.onGo(step.screen);
    if (step.screen === "audit") {
      cb.current.onOpenElectricity();
      const walk: [number, Layer][] = [[0, "total"], [4500, "category"], [8500, "calculation"], [13500, "inputs"], [17500, "source"]];
      walk.forEach(([t, l]) => timers.push(setTimeout(() => cb.current.onAuditLayer(l), t * scale)));
    } else {
      cb.current.onAuditLayer(null);
    }
    if (step.screen === "data") timers.push(setTimeout(() => cb.current.onScan(), 600 * scale));
    timers.push(setTimeout(() => { if (i >= TOUR.length - 1) cb.current.onStop(); else setI(i + 1); }, step.ms * scale));
    return () => timers.forEach(clearTimeout);
  }, [running, i, scale]);

  if (!running) return null;
  const step = TOUR[i];
  return (
    <AnimatePresence>
      <motion.div key={i} data-testid="tour-card" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="glass fixed left-6 top-20 z-[50] max-w-sm rounded-3xl p-5" style={{ background: "var(--bg)" }}>
        <p className="accent">Guided demo · {i + 1}/{TOUR.length}</p>
        <p className="mt-2 text-xl font-semibold">{step.title}</p>
        <p className="mt-2 text-[18px]">{step.body}</p>
        <div className="mt-4 flex gap-2">
          <button data-testid="tour-skip" onClick={onStop} className="btn-ghost py-1">Skip</button>
          <button data-testid="tour-next" onClick={() => (i >= TOUR.length - 1 ? onStop() : setI(i + 1))} className="rounded-full bg-ember-400 px-5 py-1 font-semibold text-ink-950 transition active:scale-95">Next</button>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
