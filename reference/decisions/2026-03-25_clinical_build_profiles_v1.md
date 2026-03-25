# Decision Memo: Clinical Build Profiles v1

- Date (UTC): `2026-03-25`
- Scope: `configs/clinical_build_profiles.yaml`, `scripts/clinical_build.py`
- Owner: `clinical-trials-repurpose-core`
- Claim IDs: `CBP-001`, `CBP-002`, `CBP-003`, `CBP-004`

## Decision
Adopt two reusable policy profiles for build cohort generation:
- `provisional_tb`: broader intake for active exploration while biochem reruns are in-flight.
- `strict_tb`: tighter, evidence-complete cohort for higher-confidence downstream clinical work products.

## Rationale
The pipeline needs two operating modes:
1. keep momentum while upstream metrics are still stabilizing
2. enforce stricter evidence quality before final clinical packaging

This is implemented as configurable policy knobs (gates + weighted scoring + top-k selection), not hardcoded per-candidate logic.

## Evidence Summary
- Source bundle: `reference/sources/semantic_scholar/20260325_200514_clinical_build_profiles_curated_candidates.*`
- Curated note: `reference/sources/semantic_scholar/2026-03-25_clinical_build_profiles_curated.md`
- Key points:
  - Repurposing benefits from systematic, staged triage and translational discipline.
  - Multi-signal prioritization (network/transcriptomic/evidence) is stronger than single-metric ranking.
  - Clinical decision layers should distinguish evidence types (RCT, observational, real-world data).

## Alternatives Considered
- Single profile only:
  - Rejected: forced tradeoff between speed and strictness; no explicit provisional/final transition.
- Per-candidate custom logic:
  - Rejected: not reusable, difficult to audit, hard to rerun consistently.
- Literature-only fixed numeric thresholds:
  - Rejected: literature supports process design, but exact cutoff values must remain target-calibrated to current score distributions.

## Risks
- Threshold drift if profiles are edited without updating this ledger.
- Apparent precision from scores may overstate confidence when upstream metrics are incomplete.
- Query-noise risk in raw literature pulls without curation.

## Follow-up Triggers
- Revisit profile thresholds after Stage B TB reruns and gate reclassification finalize.
- Revisit weighting if strict profile yields too few candidates (<5) or excessive churn between runs (>30% cohort turnover).
