::: {align="center"}
# 🌱 CarbonOS Sugar

### A Decision Support System for Traceable Carbon Accounting in Sugar Mills

**From factory data to trusted carbon insights.**

![Domain](https://img.shields.io/badge/Domain-Industrial%20Sustainability-176B4D)
![Focus](https://img.shields.io/badge/Focus-Carbon%20Accounting%20%7C%20Energy%20Analytics-246B8E)
![Status](https://img.shields.io/badge/Status-Prototype%20%7C%20Pilot%20Concept-D99A2B)

*Turning operational records into explainable emissions calculations,
energy-performance indicators, and actionable decision support.*
:::

------------------------------------------------------------------------

## The idea

Sugar mills are complex, energy-intensive facilities. Their operational
information is often distributed across electricity bills, fuel logs,
production records, weighbridge data, and other documents. Turning these
records into a consistent view of energy use and greenhouse-gas
emissions can be difficult.

**CarbonOS Sugar** is a software-first concept designed to bring these
inputs into one transparent workflow. It aims to help a sugar mill
organise factory activity data, calculate emissions using documented
factors, understand energy and emissions intensity, identify
data-quality gaps, and explore practical improvement opportunities.

> **Our central principle:** a carbon number should not be a black box.
> Every result should be explainable, reviewable, and reproducible from
> its underlying inputs.

## Why CarbonOS Sugar?

  -----------------------------------------------------------------------
  Challenge                           Our approach
  ----------------------------------- -----------------------------------
  Operational data is fragmented      Bring manual records and CSV data
                                      into a common workflow.

  Emissions calculations can be       Connect activity data, factor
  difficult to verify                 references, units, assumptions, and
                                      calculation details.

  Reports do not always translate     Present energy indicators,
  into action                         data-quality flags, and
                                      evidence-based recommendations
                                      through a Decision Support System
                                      (DSS).
  -----------------------------------------------------------------------

## How it works

``` mermaid
flowchart TD
    A([Start]) --> B[/Factory activity data<br/>Manual entry or CSV/]
    B --> C[Validate data<br/>Completeness · Units · Quality]
    C --> D{Data valid?}
    D -- No --> E[Flag issue<br/>Correct or mark unresolved]
    E --> B
    D -- Yes --> F[Map activities to applicable factors]
    F --> G[Calculate emissions<br/>and aggregate supported categories]
    G --> H{Coverage sufficient?}
    H -- No --> I[Show partial assessment<br/>and unresolved categories]
    H -- Yes --> J[Analyse performance]
    I --> J
    J --> K[Decision Support System<br/>Trends · Anomalies · Recommendations]
    K --> L[Save calculation snapshot<br/>and traceability information]
    L --> M[/Dashboard · Reports · Insights/]
    M --> N([End])
    L -. source-to-result traceability .-> B
```

### Workflow

1.  **Ingest** --- collect factory records through manual entry or
    structured CSV upload.
2.  **Validate** --- check required fields, dates, units, completeness,
    and data quality.
3.  **Map** --- associate supported activities with applicable emission
    factors.
4.  **Calculate** --- apply documented formulas and aggregate supported
    results.
5.  **Analyse** --- examine energy performance, intensity indicators,
    trends, and potential anomalies.
6.  **Support decisions** --- present findings and recommendations with
    evidence and assumptions.
7.  **Trace and report** --- retain calculation context so results can
    be inspected and reproduced.

## Designed for sugar-mill operations

The intended factory-level boundary can cover multiple operational
sources, subject to data availability and an appropriate calculation
method.

  -----------------------------------------------------------------------
  Area                                Example activity data
  ----------------------------------- -----------------------------------
  Purchased electricity               Grid electricity consumption (kWh)

  Diesel                              Generator, owned-vehicle, or
                                      equipment fuel use

  Other fossil fuels                  Fuel used in boilers and process
                                      equipment

  Bagasse                             Quantity combusted; biogenic CO₂
                                      and non-CO₂ treatment considered
                                      separately

  Cane transport                      Transport activity where boundary
                                      and supporting data are available

  Wastewater                          Effluent-treatment activity data
                                      and applicable parameters

  Refrigerants                        Refrigerant type and refill or
                                      leakage records

  Purchased energy                    Purchased steam or other supplied
                                      energy

  Production                          Cane crushed and sugar produced
  -----------------------------------------------------------------------

**Coverage note:** this is an expandable category map, not a claim that
every category is currently calculated. A category belongs in a
numerical result only when the required activity data, units, factor,
and method are available and suitable. Missing or unsupported categories
are shown as unresolved or not assessed---not silently treated as zero.

Process-stage analysis requires stage-level measurements. Whole-factory
inputs are not arbitrarily distributed across individual process stages.

## What makes it different?

### 1. Traceability by design

The intended traceability layer connects each reported result to:

-   The source activity record and reporting period.
-   The quantity and unit used.
-   The emission factor and its source reference.
-   Any unit conversion or calculation step.
-   The formula and resulting value.
-   Provenance, assumptions, and data-quality warnings.
-   The calculation snapshot and engine version.

This is a software traceability approach---not a claim of blockchain or
tamper-proof storage.

### 2. Transparent calculations

  -----------------------------------------------------------------------------------------------------------
  Indicator                           Formula
  ----------------------------------- -----------------------------------------------------------------------
  Emissions                           `Activity Data × Emission Factor`

  Energy intensity                    `Energy consumed ÷ Production`

  Emissions intensity                 `Assessed emissions ÷ Production`

  Period change                       `(Current intensity − Previous intensity) ÷ Previous intensity × 100`
  -----------------------------------------------------------------------------------------------------------

For example, electricity emissions require electricity consumption and a
factor expressed in compatible units, such as `kg CO₂e/kWh`. Results
should retain calculation precision internally and apply rounding only
for display.

### 3. A Decision Support System---not just a calculator

CarbonOS Sugar is intended to connect accounting with operational
interpretation:

-   **Performance indicators:** energy and emissions intensity where
    production data is available.
-   **Data-quality alerts:** missing values, incompatible units, or
    unsupported categories.
-   **Anomaly screening:** transparent checks against historical or
    defined reference values.
-   **Recommendations:** potential actions accompanied by evidence,
    assumptions, verification steps, and additional data requirements.

Recommendations are decision-support prompts, not guaranteed savings or
automated engineering instructions.

## Planned outputs

-   Factory carbon dashboard.
-   Category-wise emissions inventory.
-   Energy-performance indicators.
-   Data-quality and unresolved-category report.
-   Emission-factor register.
-   Anomaly flags and review prompts.
-   Evidence-linked improvement recommendations.
-   Calculation history and traceability view.
-   Downloadable reports or data exports.

Output availability depends on the implementation stage and the quality
and completeness of supplied data.

## Calculation integrity and data policy

CarbonOS Sugar follows a conservative accounting approach:

-   **No silent zeroes:** missing data or factors do not become zero
    emissions.
-   **No unsupported factors:** each factor should have a value, unit,
    geography, applicable period, source, and review status.
-   **Clear provenance:** distinguish user-provided data, published
    factors, derived values, synthetic examples, and unknown
    information.
-   **Visible limitations:** partial assessments are labelled as partial
    when categories remain unresolved.
-   **Separate biogenic treatment:** bagasse-related biogenic CO₂ is
    distinguished from fossil emissions, with non-CO₂ treatment
    documented according to the selected method.
-   **No invented allocation:** product or process-stage allocation is
    not performed without a defensible method and supporting data.
-   **Versioned results:** changes to inputs or factors should create a
    new calculation snapshot rather than silently rewriting historical
    results.

### Reference frameworks and data sources

These are starting points for selecting and documenting methods and
emission factors. A reference is not, by itself, proof that a particular
factor is applicable.

-   [Central Electricity Authority (CEA) --- CO₂ Baseline
    Database](https://cea.nic.in/cdm-co2-baseline-database/?lang=en)
-   [GHG Protocol](https://ghgprotocol.org/)
-   [IPCC Emission Factor
    Database](https://www.ipcc-nggip.iges.or.jp/EFDB/main.php)
-   [India GHG Program --- Calculation
    Tools](https://indiaghgp.org/calculation-tools)
-   [TERI --- Indian sugar-sector
    report](https://www.teriin.org/sites/default/files/2021-08/Sugar_Report.pdf)

Before operational use, each selected factor must be checked for its
value, units, geography, year, gases covered, system boundary, source
location, and applicability.

## Prototype technology

The rapid-prototype direction is intentionally lightweight:

  -----------------------------------------------------------------------
  Layer                   Proposed technology     Role
  ----------------------- ----------------------- -----------------------
  User interface          Streamlit               Data entry, uploads,
                                                  dashboards, and review
                                                  screens

  Calculation logic       Python                  Unit-aware calculations
                                                  and validation

  Data handling           pandas                  Structured
                                                  activity-data
                                                  processing

  Persistence             SQLite                  Prototype records and
                                                  calculation history

  Quality assurance       pytest                  Calculation,
                                                  validation, import, and
                                                  traceability tests
  -----------------------------------------------------------------------

The calculation engine is intended to remain separate from the user
interface so it can later support a larger architecture, such as
React/Vite, FastAPI, and PostgreSQL.

## Suggested repository structure

``` text
carbonos-sugar/
├── app.py
├── calculations.py
├── database.py
├── imports.py
├── seed_data.py
├── reporting.py
├── requirements.txt
├── README.md
├── METHODOLOGY.md
├── sample_data/
│   └── demo_activities.csv
└── tests/
    ├── test_calculations.py
    ├── test_validation.py
    ├── test_traceability.py
    └── test_imports.py
```

The actual repository may differ as implementation evolves.

## Getting started

### Prerequisites

-   Python 3.10 or later
-   Git
-   pip

### 1. Clone the repository

``` bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd carbonos-sugar
```

### 2. Create and activate a virtual environment

**Windows**

``` bash
python -m venv .venv
.venv\Scripts\activate
```

**macOS / Linux**

``` bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

``` bash
pip install -r requirements.txt
```

### 4. Run the application

``` bash
streamlit run app.py
```

If the repository uses a different entry point, follow the run command
documented in its application configuration.

## Demo data and responsible interpretation

A demonstration may use synthetic factory records to show the end-to-end
workflow. Synthetic data is useful for testing the interface and
calculation pipeline, but it is not evidence of actual mill performance.

For example:

`12,500 kWh × 0.70 kg CO₂e/kWh = 8,750 kg CO₂e`

This is only a mathematical demonstration. The factor shown is
**synthetic and illustrative**, not a verified current Indian grid
emission factor. It must not be used for real disclosures, compliance,
investment decisions, or sustainability claims.

## Current scope and limitations

CarbonOS Sugar is a prototype and pilot concept. It is designed to
demonstrate a practical approach to factory-level carbon accounting and
energy decision support.

Do not assume the following unless separately implemented and validated:

-   Complete emissions coverage for every sugar-mill activity.
-   A verified partnership with or deployment at a specific factory.
-   Independently validated emissions or energy savings.
-   Certified carbon accounting or regulatory compliance.
-   Product-level footprints or allocation across sugar, ethanol,
    molasses, bagasse, and exported electricity.
-   Predictive AI or guaranteed optimisation outcomes.

A real pilot requires factory access, source records, agreement on the
organisational and operational boundary, and review of the selected
calculation methods and factors.

## Roadmap

-   [ ] Complete the core activity-data and factor data model.
-   [ ] Support manual entry and CSV ingestion through a common
    validation pipeline.
-   [ ] Implement unit-aware calculations for supported categories.
-   [ ] Add calculation snapshots and source-to-result traceability.
-   [ ] Build factory-level emissions and energy dashboards.
-   [ ] Add transparent data-quality and anomaly checks.
-   [ ] Generate evidence-linked recommendations and exports.
-   [ ] Validate the workflow with real factory records and domain
    review.
-   [ ] Expand category coverage as suitable data and methods become
    available.

## Project vision

**Make industrial carbon accounting understandable, traceable, and
useful for everyday operational decisions.**

CarbonOS Sugar aims to help sugar mills move from scattered operational
records to a clearer picture of energy use and emissions---while keeping
the evidence and limitations visible at every step.

------------------------------------------------------------------------

::: {align="center"}
**CarbonOS Sugar**\
*Measure clearly. Trace every result. Support better decisions.*
:::
