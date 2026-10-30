# CarbonOS Sugar — Methodology and Limitations

Prototype status: **not independently verified, not certified, not validated in an operating sugar mill.**
All bundled data is FICTIONAL.

## 1. Boundary
Factory-level greenhouse-gas inventory and energy-performance tool. It is **not** a product carbon footprint,
does not allocate between sugar / ethanol / molasses / bagasse / exported power, and is not a lifecycle assessment.
The boundary text and production quantities are entered by the user and are not verified.
A category may be declared outside the boundary (with a reason, only if it has no records); it is then shown as
`excluded`, never hidden.

## 2. Categories
| Category | Prototype treatment |
|---|---|
| Purchased electricity | Calculated if an active factor exists (kWh or MWh) |
| Diesel combustion | Calculated if an active factor exists (L or kL) |
| Other fossil fuels | Calculated only if a factor with a compatible unit exists |
| Purchased steam / energy | Calculated only if a compatible factor exists |
| Cane transport | tonne-km records; calculated only if a compatible factor exists |
| Refrigerants | kg records; calculated only if a documented kgCO2e/kg factor exists |
| Bagasse combustion | **Not assessed.** Biogenic CO2 and CH4/N2O treatment are not implemented; bagasse is never added to the fossil total |
| Wastewater & effluent | **Not assessed.** No method implemented |
| Other sources | **Not assessed** |

Process-stage allocation is not performed. Whole-factory electricity is reported as factory-level.

## 3. Calculation
`Emissions (kgCO2e) = quantity × factor`, using exact decimal arithmetic (no binary-float error). Full precision is
stored; rounding happens only for display. Results are converted to tonnes only for display/export (÷1000).

Only these conversions are defined, and each one applied is written into the result:
MWh↔kWh, kL↔L, t↔kg; and factor numerator tCO2e→kgCO2e. Anything else (e.g. litres vs a per-tonne factor, which
would need a density) is a `unit_mismatch` and is **not** calculated. A factor numerator other than kgCO2e/tCO2e
(e.g. CO2-only) is rejected.

Unit synonyms accepted on input are listed in `calculations.UNIT_SYNONYMS` (e.g. `litres`→`L`). Date format is strictly
`YYYY-MM-DD`; quantities must be plain numbers (a comma is rejected rather than guessed).

## 4. Statuses
| Status | Meaning |
|---|---|
| `calculated` | Numeric result produced |
| `missing_activity_data` | Quantity absent — never treated as zero |
| `missing_factor` | No usable factor — never treated as zero |
| `unit_mismatch` | Units incompatible / unsupported, no documented conversion |
| `illustrative_factor` | Factor illustrative; blocked in real-reporting mode |
| `needs_review` | Negative/unusable value, unknown provenance, or synthetic record in real mode |
| `not_assessed` | Category/method not supported |
| `stale` | Shown on a snapshot when inputs changed after it was calculated |

## 5. Inventory completeness
A category is `all_records_calculated` only when every recorded record calculated. This does **not** verify that the
records cover the whole period. The inventory is `incomplete` unless every non-excluded category is fully calculated;
the total is then labelled **Partial assessed total**. `unresolved_count` = unresolved records + categories not fully
assessed. Synthetic/illustrative contributions are totalled separately.

## 6. Factor policy
* The prototype ships **no real emission factors**. The two demo factors (`EF-ELECTRICITY-DEMO-001` = 0.70
  kgCO2e/kWh, `EF-DIESEL-DEMO-001` = 2.50 kgCO2e/L) are round fictional numbers marked `illustrative` /
  `synthetic_demo`. They are not published factors.
* Starting points for sourcing real factors (not proof of any value): CEA CO₂ Baseline Database, the TERI Indian
  sugar-sector report, GHG Protocol. Before use, verify value, units, geography, year, boundary, gases, CO2 vs CO2e,
  source location and suitability.
* A factor can be saved as `verified_for_use` only with organisation, document, geography, year and a URL or
  page reference, and not with synthetic/unknown provenance. This is a completeness check on *your* attestation;
  the app cannot verify the number.
* **Real-reporting mode** calculates only `verified_for_use` factors with non-synthetic, non-unknown activity data.

## 7. Provenance
Activity: `user_provided`, `synthetic_demo`, `unknown`. Factors additionally: `published_factor`,
`published_benchmark`, `derived`. Results are `derived`. Reports break out each type, plus missing/unresolved.

## 8. Traceability and history
Each calculation run stores an immutable snapshot: the activity record and factor as they were, the formula,
conversion, result, timestamps, engine version and mode. Later edits change only live rows. The app recomputes each
traced result from snapshot fields alone and shows whether it matches. Database triggers abort UPDATE/DELETE on
snapshots, results and audit events. **This is not tamper-proof**: anyone with file access can drop the triggers.
A snapshot is `stale` if a change event for its period (or any factor) occurred after it.

## 9. Energy indicators and flags
Intensity = energy ÷ production, factory-wide, only when numerator complete and denominator present and > 0.
Flags are transparent rules (thresholds: record vs. median ±50%, intensity vs. previous period ±20%): missing
quantity, duplicate-looking records, outliers, zero production with energy, fuel without factor, unapproved factor,
missing source reference, trend change. Each states why it fired. A flag is not a diagnosis. Recommendations are
either tied to an observation or labelled *generic*; no savings figures are produced.

## 10. Known limitations
* Not validated with real mill data; no factory partner exists.
* No real factors included; real reporting needs factors you source and verify.
* Bagasse/biogenic, wastewater, process-stage allocation, product footprints and Scope 3 are not implemented.
* Single-user, local SQLite, no authentication.
* Boundary comparability between periods is user-asserted.
* Float storage (REAL) of inputs; calculation uses decimal arithmetic on their shortest decimal representation.
