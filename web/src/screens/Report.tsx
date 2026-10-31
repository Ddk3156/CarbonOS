import { FictionalBadge, Pill } from "../components/ui";
import { kg, tonnes } from "../lib/format";
import { exportUrl } from "../lib/api";
import { humanStatus } from "../lib/labels";
import type { Bootstrap } from "../lib/schema";

function saveText(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/markdown" }));
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function Report({ data, offline }: { data: Bootstrap; offline: boolean }) {
  const snap = data.snapshot;
  const totals = snap?.summary?.inventory?.totals;
  const cats: any[] = (snap?.summary?.inventory?.categories ?? []).filter((c: any) => c.n_records > 0);
  const sid = snap?.id;
  const md = data.report_markdown ?? "";
  return (
    <section data-testid="screen-report" className="min-h-dvh px-4 pb-32 pt-8">
      <div className="mx-auto max-w-3xl">
        <FictionalBadge />
        <div className="relative mt-6 rounded-[28px] border-4 border-double p-8 shadow-glass" style={{ background: "#f7f1e8", color: "#1a140c", borderColor: "#b86a1c" }} data-testid="certificate">
          <p className="text-center text-[18px] tracking-[0.3em]">CARBONOS SUGAR</p>
          <h1 className="mt-3 text-center font-serif text-4xl">Emissions statement</h1>
          <p className="mt-2 text-center text-xl">{data.factory?.name}</p>
          <p className="text-center text-[18px]">{data.period?.start_date} to {data.period?.end_date}</p>
          <p className="mt-6 text-center text-6xl font-semibold" data-testid="cert-total">{tonnes(totals?.assessed_kg_co2e)}</p>
          <div className="mt-3 flex justify-center"><span className="rounded-full px-4 py-1 text-[18px] font-semibold" style={{ background: "#f3d9a8" }}>Partial</span></div>
          <table className="mx-auto mt-6 w-full max-w-md text-[18px]">
            <tbody>
              {cats.map((c) => (
                <tr key={c.category} className="border-t" style={{ borderColor: "#d6c7aa" }}>
                  <td className="py-1.5">{c.label}</td>
                  <td className="py-1.5 text-right font-semibold">{c.assessed_kg_co2e == null ? humanStatus(c.completeness) : kg(c.assessed_kg_co2e)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-5 text-center text-[18px]">Not independently verified. Not a mill validation. Unresolved rows are left out, never counted as zero.</p>
          <p className="absolute -right-3 -top-3 rotate-6 rounded-md border-4 px-3 py-1 text-[18px] font-bold" style={{ borderColor: "#b86a1c", color: "#b86a1c", background: "#f7f1e8" }}>FICTIONAL DEMO</p>
        </div>
        <div className="mt-6 flex flex-wrap items-center gap-3">
          {sid && !offline && <a data-testid="download-bundle" href={exportUrl(sid)} download className="btn-primary inline-block">Download report and all data</a>}
          <button data-testid="download-md" disabled={!md} onClick={() => saveText("carbonos-sugar-report.md", md)} className={offline ? "btn-primary" : "btn-ghost"}>
            {offline ? "Download the report" : "Report only"}
          </button>
          <Pill tone="warn">Fictional mill · illustrative factors</Pill>
        </div>
        {offline && <p className="mt-3 text-[18px] muted">Offline: the full data bundle needs the live API.</p>}
      </div>
    </section>
  );
}
