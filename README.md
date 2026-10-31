<b>CarbonOS Sugar</b>

Traceable Carbon Accounting & Energy Performance Intelligence for the Sugar Industry

Turning fragmented industrial activity data into transparent, traceable, and reviewable emissions intelligence.

<p align="center">
  <strong>Industrial Sustainability · Carbon Accounting · Energy Analytics · Audit Traceability</strong>
</p>

1. Overview

CarbonOS Sugar is a prototype industrial carbon-accounting and energy-performance platform designed specifically for sugar manufacturing facilities.

The platform transforms fragmented operational records—including electricity consumption, fuel usage, and production data—into a structured greenhouse gas (GHG) inventory with transparent calculations and end-to-end traceability.

Built around the workflow proposed in the CarbonOS Industrial research concept, this prototype focuses on demonstrating how industrial facilities can move from disconnected operational records to evidence-based emissions reporting.

Every calculated result can be traced back to its original activity record, emission factor, calculation methodology, unit conversion, and data provenance.

«Prototype Disclosure: CarbonOS Sugar is a research and demonstration prototype. It has not been validated in an operating sugar mill, independently verified, or certified. All bundled demonstration data is fictional.»

2. The Problem

Industrial sustainability reporting often relies on operational information distributed across electricity bills, fuel registers, production records, and manually maintained spreadsheets.

This fragmentation creates several challenges:

- Data Fragmentation: Operational information is distributed across multiple records and formats.
- Limited Traceability: Reported emissions may be difficult to reconcile with their underlying source documents.
- Calculation Inconsistency: Different units, conversion methods, and emission factors can introduce inconsistencies.
- Incomplete Reporting: Missing activity data or emission factors can result in misleading inventory totals.
- Limited Auditability: Reviewing the origin and calculation of individual emissions values can be time-consuming.

The CarbonOS Approach

CarbonOS Sugar introduces a structured workflow that connects operational activity data with emission factors, calculation logic, and reporting outputs.

Instead of presenting emissions as isolated numbers, the platform makes each result reviewable through its underlying evidence and calculation history.

---

3. Core Capabilities

All features described below have been implemented and covered by automated tests.

3.1 Industrial Data Management

- Factory and reporting-period configuration.
- Clearly defined organizational and reporting boundaries.
- Optional declaration of reporting exclusions.
- Manual activity-data entry.
- CSV-based bulk data ingestion.
- Import preview and row-level validation.
- Explicit error reporting without silently discarding records.

3.2 Emission Factor Management

- Centralized emission-factor library.
- Factor status and provenance tracking.
- Source documentation and factor metadata.
- Separation of illustrative and reporting-eligible factors.
- Illustrative factors are blocked in real-reporting mode.

Factor Integrity: No real emission factors are bundled with the prototype. Users must independently source and verify factors before using them for actual reporting.

3.3 Calculation Engine

- Independent Python calculation engine, separated from the user interface.
- Exact-decimal arithmetic for calculation accuracy.
- Unit validation and supported unit conversions.
- Factor-based emissions calculations.
- Explicit handling of incomplete and unsupported records.

The platform follows an important reporting principle:

Missing information is never interpreted as zero emissions.

Missing activity data, unavailable emission factors, and unsupported categories remain explicitly unresolved.

Where applicable, calculated totals are labelled Partial, preventing incomplete inventories from being presented as complete assessments.

3.4 Energy Performance Intelligence

The platform calculates factory-level energy-performance indicators wherever sufficient data is available.

Supported indicators include:

Indicator| Measurement
Electricity intensity per tonne of cane| kWh/t cane
Electricity intensity per tonne of sugar| kWh/t sugar
Diesel intensity per tonne of cane| L/t cane

Additional capabilities include:

- Transparent operational anomaly flags.
- Observation-based recommendations.
- Clearly labelled generic recommendations where operational observations are unavailable.

3.5 End-to-End Traceability

Traceability is a central design principle of CarbonOS Sugar.

Users can select an emissions result and navigate backwards through its calculation lineage.

Result → Activity Record → Emission Factor Snapshot → Formula → Unit Conversion → Provenance

Each traceability record includes:

- Original activity information.
- Emission-factor snapshot.
- Calculation formula.
- Unit conversion details.
- Data provenance.
- Calculation timestamp.
- Engine version.
- Immutable calculation snapshot ID.
- Re-computation verification.

This enables users and reviewers to understand not only the reported emissions value, but also how it was derived.

3.6 Audit and Reporting

- Immutable calculation snapshots.
- Detection of changes that make previous calculations stale.
- Historical snapshot comparison.
- Calculation audit history.
- CSV exports.
- Markdown-based reports.
- ZIP-based reporting bundles generated from stored calculation snapshots.

---

4. Technology Stack

Layer| Technology
Primary Application| Python, Streamlit
Database| SQLite
Data Processing| Pandas
Calculation Engine| Python Decimal
Testing| Pytest
Pitch Interface| React, TypeScript
Frontend Build Tool| Vite
Styling| Tailwind CSS
Animation| Framer Motion
Data Visualization| Recharts
Command Interface| cmdk
API Layer| FastAPI
E2E Testing| Playwright

The original Python calculation engine remains unchanged in the pitch architecture. FastAPI provides an interface for the React frontend to access the underlying application functionality.

---

5. Architecture

CarbonOS Sugar follows a modular architecture separating data management, calculation logic, and presentation.

Core Application

Streamlit → Application Logic → Calculation Engine → SQLite

Pitch Demonstration Interface

React Frontend → FastAPI → Existing Python Engine → SQLite

An offline demonstration mode is also available through a locally generated JSON fallback dataset.

If the API is unavailable, the React interface can use:

"web/public/fallback/bootstrap.json"

This enables the pitch demonstration to continue without an active backend connection.

---

6. Installation and Setup

Prerequisites

- Python 3.10 or later.
- pip.
- Git.

Clone the Repository

git clone <repository-url>
cd carbonos-sugar

Create a Virtual Environment

python -m venv .venv

Activate it:

Windows PowerShell

.venv\Scripts\Activate.ps1

Linux / macOS

source .venv/bin/activate

Install Dependencies

pip install -r requirements.txt

Run Automated Tests

pytest

Launch the Application

streamlit run app.py

The default database is "carbonos.db" in the working directory.

To specify a different database location:

CARBONOS_DB=/path/file.db

---

7. Demonstration Environment

CarbonOS Sugar includes a synthetic demonstration dataset to showcase the complete workflow.

Loading Demo Data

From the application:

Setup → Load Synthetic Demo Dataset

Select Skip current-period records if you want to demonstrate the CSV import workflow independently.

Alternatively, run:

python seed_data.py

To skip current-period records:

python seed_data.py --no-current-records

Demonstration Calculation

The following example illustrates how the calculation engine processes fictional operational records.

Activity| Quantity| Illustrative Factor| Emissions
Grid Electricity| 46,000 kWh| 0.70 kg CO₂e/kWh| 32,200 kg
Diesel| 800 + 750 + 900 L| 2.50 kg CO₂e/L| 6,125 kg
Total| | | 38,325 kg

Assessed Partial Total: 38.325 t CO₂e

These values are strictly fictional and use illustrative emission factors. They must not be interpreted as actual sugar-mill emissions or verified environmental performance.

Generated demonstration exports are available in:

"sample_data/exports/"

---

8. CSV Data Integration

The platform supports structured CSV imports for operational activity records.

Supported Format

activity_date,category,activity_name,quantity,unit,source_reference,provenance,notes
2026-01-01,purchased_electricity,Grid electricity,12500,kWh,DEMO-BILL-001,synthetic_demo,Fictional demonstration record

Required Fields

- "activity_date"
- "category"
- "activity_name"
- "quantity"
- "unit"
- "provenance"

Supported Provenance Values

Provenance| Description
user_provided| Data entered or supplied by a user
synthetic_demo| Artificial data generated for demonstration
unknown| Data whose origin has not been established

Supported activity categories and units are documented in "METHODOLOGY.md" and displayed on the CSV import screen.

The file "sample_data/demo_activities_with_errors.csv" demonstrates the platform's validation and rejection mechanisms.

---

9. Methodology and Emission Factor Policy

The detailed methodology, calculation boundaries, supported categories, data provenance rules, and factor-handling policies are documented in:

"METHODOLOGY.md"

The current prototype does not bundle independently verified real-world emission factors.

Potential starting points for sourcing and reviewing factors include:

- Central Electricity Authority (CEA) CO₂ Baseline Database.
- TERI research publications on the Indian sugar industry.
- GHG Protocol accounting and reporting guidance.

These references are starting points for research and factor verification, not automatic validation of any particular emission-factor value.

Actual reporting requires appropriate source selection, verification, documentation, and applicability assessment.

---

10. Pitch Demonstration Interface

The judge-facing demonstration interface is available in the "web/" directory.

It uses a modern frontend architecture built with:

- React and TypeScript.
- Vite.
- Tailwind CSS.
- Framer Motion.
- Recharts.
- cmdk.

The frontend communicates with "api/server.py", which provides a FastAPI interface to the existing Python calculation engine.

Quick Start

Install the complete environment:

npm run setup

Launch the demonstration:

npm run demo

Open:

"http://127.0.0.1:5173"

Additional Commands

Regenerate the offline fallback:

npm run fallback

Run end-to-end tests:

npm run test:e2e

Run the end-to-end test suite 10 consecutive times:

npm run test:e2e:10

Run the full 90-second demonstration tour test:

FULL_TOUR=1 npm run test:e2e

The Playwright test workflow resets the demonstration environment before execution and checks for browser console errors.

Demonstration Controls

Fictional Demo Factor

The demonstration includes an option to add a fictional, explicitly unsourced emission factor for the mill/coal data gap. This illustrates how an unresolved calculation can become assessable when a factor is supplied.

This is a demonstration-only operation and does not establish the validity of the factor.

Reset Demo

The demonstration can be restored to its initial state using:

- Data Room → Reset Demo.
- "Ctrl + K" or "Cmd + K".

Pitch Configuration

Presentation budget figures are sourced exclusively from:

"pitch.config.json"

The current pitch configuration uses ₹60,000, whereas an earlier research deck referenced ₹30,000.

Set:

{
  "showReconcileNote": true
}

to display a presenter-facing reconciliation warning on the Ask screen.

---

11. Current Limitations

CarbonOS Sugar is an early-stage prototype. Its present scope is intentionally limited.

Validation and Deployment

- Not validated in an operating sugar mill.
- No industrial implementation partner.
- Not independently verified or certified.
- No real-world operational performance claims.

Accounting Scope

- Bagasse and biogenic emissions treatment not implemented.
- Wastewater emissions not implemented.
- By-product allocation not implemented.
- Product carbon footprints not implemented.
- Scope 3 accounting not implemented.
- No complete lifecycle assessment.

Technical Scope

- Single-user local SQLite architecture.
- Audit history is not tamper-proof.
- No production-grade multi-user infrastructure.
- No direct integration with industrial meters or ERP systems.

---

12. Development Roadmap

The following capabilities represent planned future development and are not part of the current implementation.

Development Area| Planned Enhancement
Emission Factors| Verified India-specific emission-factor library
By-product Accounting| Ethanol, jaggery, molasses and other product allocation
Biogenic Emissions| Bagasse and biogenic carbon accounting
Wastewater| Wastewater treatment and associated emissions
Data Integration| Industrial sub-meter and operational data integration
Infrastructure| Migration to React, FastAPI and PostgreSQL
Validation| Field testing and collaboration with partner sugar mills

The long-term objective is to evolve CarbonOS from a demonstrative accounting workflow into a scalable industrial sustainability intelligence platform.

---

13. Research and Development Positioning

CarbonOS Sugar demonstrates a practical approach to connecting industrial activity data, carbon accounting, energy-performance indicators, and audit traceability.

Its primary technical contribution is not simply calculating an emissions total, but preserving the relationship between reported results and the underlying evidence.

The prototype explores three important principles:

1. Evidence-Driven Accounting: Every calculated result should have an identifiable source and documented calculation methodology.
2. Transparent Uncertainty: Missing information and unsupported calculations should remain visible rather than being silently interpreted as zero.
3. Reproducible Reporting: Calculation snapshots should preserve the inputs, factors, and engine information needed to review and reproduce historical results.

---

14. License

No open-source license has been selected for this repository yet.

---

15. Project Status

Current Stage: Functional Prototype / Pitch Demonstration

Implementation: Core features implemented and covered by automated tests.

Industrial Validation: Pending.

Independent Verification: Not performed.

Certification: Not obtained.

Demo Video: Not yet recorded.

---

CarbonOS Sugar

Making Industrial Carbon Data Traceable, Transparent, and Actionable.
