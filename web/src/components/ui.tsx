import { Component, type ErrorInfo, type ReactNode, useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";

export function CountUp({ value, digits = 3, className = "", testId, duration = 1400 }: { value: number; digits?: number; className?: string; testId?: string; duration?: number }) {
  const reduce = useReducedMotion();
  const [n, setN] = useState(reduce ? value : 0);
  useEffect(() => {
    if (reduce) { setN(value); return; }
    const start = performance.now();
    let raf = 0;
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / duration);
      setN(value * (1 - (1 - p) ** 3));
      if (p < 1) raf = requestAnimationFrame(tick); else setN(value);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, reduce, duration]);
  return <span data-testid={testId} className={className}>{n.toLocaleString("en-IN", { maximumFractionDigits: digits, minimumFractionDigits: digits })}</span>;
}

export function FictionalBadge({ className = "" }: { className?: string }) {
  return (
    <span data-testid="fictional-badge" className={`inline-flex items-center whitespace-nowrap rounded-full border border-ember-400/60 bg-ember-400/15 px-3 py-1 text-[18px] font-semibold tracking-wide accent ${className}`}>
      FICTIONAL DEMO
    </span>
  );
}

export function Pill({ children, tone = "neutral", testId }: { children: ReactNode; tone?: "neutral" | "warn" | "ok" | "bad"; testId?: string }) {
  const map = {
    neutral: "border-[color:var(--stroke)] bg-[color:var(--glass)]",
    warn: "border-ember-400/50 bg-ember-400/15 accent",
    ok: "border-emerald-400/50 bg-emerald-400/15 text-[color:var(--ok)]",
    bad: "border-rose-400/50 bg-rose-400/15 text-[color:var(--bad)]",
  };
  return <span data-testid={testId} className={`inline-flex items-center whitespace-nowrap rounded-full border px-3 py-1 text-[18px] font-medium ${map[tone]}`}>{children}</span>;
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-2xl bg-[color:var(--glass-strong)] ${className}`} />;
}

export class ScreenErrorBoundary extends Component<{ name: string; children: ReactNode }, { err: string | null }> {
  state = { err: null as string | null };
  static getDerivedStateFromError(e: Error) { return { err: e.message }; }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error(this.props.name, error, info); }
  render() {
    if (this.state.err) {
      return (
        <div data-testid="screen-error" className="glass mx-auto mt-24 max-w-lg rounded-3xl p-8">
          <p className="text-xl font-semibold">This screen could not render</p>
          <p className="mt-2 text-[18px] muted">Use the dock to open another screen. The other screens are unaffected.</p>
        </div>
      );
    }
    return this.props.children;
  }
}

function ToastItem({ id, text, onDone }: { id: string; text: string; onDone: (id: string) => void }) {
  useEffect(() => { const t = setTimeout(() => onDone(id), 3600); return () => clearTimeout(t); }, [id, onDone]);
  return (
    <motion.div initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} role="status" className="pointer-events-auto glass max-w-sm rounded-2xl px-4 py-3 shadow-glass" style={{ background: "var(--bg)" }}>
      {text}
    </motion.div>
  );
}

export function ToastHost({ toasts, onDone }: { toasts: { id: string; text: string }[]; onDone: (id: string) => void }) {
  return (
    <div className="pointer-events-none fixed right-6 top-20 z-[80] space-y-3">
      <AnimatePresence>{toasts.map((t) => <ToastItem key={t.id} id={t.id} text={t.text} onDone={onDone} />)}</AnimatePresence>
    </div>
  );
}

export function Confetti({ show }: { show: boolean }) {
  const reduce = useReducedMotion();
  if (!show || reduce) return null;
  const bits = Array.from({ length: 40 }, (_, i) => i);
  return (
    <div className="pointer-events-none fixed inset-0 z-[90] overflow-hidden" data-testid="confetti">
      {bits.map((i) => (
        <span key={i} className="absolute h-2.5 w-3.5 rounded-sm" style={{ left: `${(i * 37) % 100}%`, top: "-12px", background: ["#e8a15a", "#f4eee4", "#7ee2b0", "#8fb4ff"][i % 4], animation: `fall ${1.1 + (i % 5) * 0.18}s ease-in ${(i % 7) * 0.05}s forwards`, transform: `rotate(${i * 12}deg)` }} />
      ))}
      <style>{`@keyframes fall { to { transform: translateY(110vh) rotate(260deg); opacity: 0.2; } }`}</style>
    </div>
  );
}

function useEscape(open: boolean, onClose: () => void) {
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);
}

export function Sheet({ open, title, onClose, children, testId }: { open: boolean; title: string; onClose: () => void; children: ReactNode; testId?: string }) {
  useEscape(open, onClose);
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.button aria-label="Close" className="fixed inset-0 z-[60] bg-black/55" onClick={onClose} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
          <motion.div role="dialog" aria-label={title} data-testid={testId} initial={{ y: "100%" }} animate={{ y: 0 }} exit={{ y: "100%" }} transition={{ type: "spring", damping: 28, stiffness: 300 }} className="glass fixed inset-x-0 bottom-0 z-[70] max-h-[80vh] overflow-auto rounded-t-3xl p-6 pb-28" style={{ background: "var(--bg)" }}>
            <div className="mx-auto mb-4 h-1.5 w-12 rounded-full bg-[color:var(--stroke)]" />
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-2xl font-semibold">{title}</h2>
              <button onClick={onClose} className="btn-ghost">Close</button>
            </div>
            {children}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

export function Drawer({ open, title, onClose, children, testId }: { open: boolean; title: string; onClose: () => void; children: ReactNode; testId?: string }) {
  useEscape(open, onClose);
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.button aria-label="Close" className="fixed inset-0 z-[60] bg-black/55" onClick={onClose} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
          <motion.aside role="dialog" aria-label={title} data-testid={testId} initial={{ x: "-100%" }} animate={{ x: 0 }} exit={{ x: "-100%" }} transition={{ type: "spring", damping: 28, stiffness: 300 }} className="glass fixed inset-y-0 left-0 z-[70] w-full max-w-md overflow-auto p-6" style={{ background: "var(--bg)" }}>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-2xl font-semibold">{title}</h2>
              <button onClick={onClose} className="btn-ghost">Close</button>
            </div>
            {children}
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
