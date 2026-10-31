export const STATUS: Record<string, string> = {
  calculated: "Calculated",
  missing_activity_data: "Needs a quantity",
  missing_factor: "Needs a factor",
  unit_mismatch: "Units incompatible",
  illustrative_factor: "Illustrative factor",
  needs_review: "Needs review",
  not_assessed: "Not covered yet",
  stale: "Out of date",
  valid: "Ready",
  rejected: "Rejected",
  incomplete: "Incomplete",
  partial: "Partial",
  all_records_calculated: "Calculated",
  unresolved: "Needs a factor",
  excluded: "Outside boundary",
  verified_for_use: "Verified for use",
  illustrative: "Illustrative",
  deprecated: "Deprecated",
  synthetic_demo: "Fictional demo",
  user_provided: "Entered by you",
  published_factor: "Published factor",
  published_benchmark: "Published benchmark",
  derived: "Derived",
  unknown: "Unknown",
  demo: "Demo",
  real: "Real reporting",
};

export function humanStatus(code: string | null | undefined): string {
  if (!code) return "Unknown";
  return STATUS[code] ?? code.replace(/_/g, " ");
}

/** Engine messages list every valid value and use snake_case keys; show the plain first sentence only. */
export function plainError(msg: string): string {
  return msg
    .split(" Valid:")[0]
    .replace(/'([a-z]+(?:_[a-z]+)+)'/g, (_m, k) => `'${k.replace(/_/g, " ")}'`);
}
