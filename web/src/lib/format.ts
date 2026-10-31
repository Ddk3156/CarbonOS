export function fmtNum(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toLocaleString("en-IN", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function kg(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return `${fmtNum(n, n % 1 === 0 ? 0 : 2)} kg`;
}

export function tonnes(kgVal: number | null | undefined): string {
  if (kgVal === null || kgVal === undefined) return "—";
  return `${fmtNum(kgVal / 1000, 3)} t CO₂e`;
}

export function prettyDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = iso.slice(0, 10);
  return d;
}

export function deltaChip(before: number | null | undefined, after: number | null | undefined): string {
  if (before == null || after == null) return "No numeric result";
  const d = after - before;
  const sign = d > 0 ? "+" : "";
  return `${sign}${fmtNum(d, 2)} kg`;
}

/** Quantities: no trailing zeros (13,000 not 13,000.00; 0.9 stays 0.9). */
export function fmtQty(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toLocaleString("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 0 });
}
