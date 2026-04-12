# Clinical Pipeline Model (Canonical Link)

Last updated: 2026-04-11

## Canonical Source

Shared live pipeline-state canonical source:
- `/home/seth/dev/medicine/biochem-pipeline-core/docs/PIPELINE_CANONICAL_STATE.md`

Historical architecture/model reference (non-canonical):
- `/home/seth/dev/medicine/biochem-pipeline-core/docs/PIPELINE_MODEL.md`

This file is intentionally thin to prevent drift from the suite canonical model.

## Clinical Local Model (What This Repo Owns)

Primary clinical operating docs:
- `docs/CLINICAL_BUILD_MODEL.md`
- `docs/SUITE_ORCHESTRATION.md`
- `docs/COST_OPTIMIZED_COMPUTE_PLAN.md`

These docs are authoritative for clinical-only behavior and operators should prioritize them for day-to-day execution.

## Current Clinical Delta (Operational)

- Intake/build workflow from biochem handoff is active.
- Build profiles and reusable scoring gates are active.
- Supervised orchestration exists (`run-once`, checkpoints, approvals).
- Clinical evidence lanes are production-usable for provisional and strict build outputs.
- Any shared tier semantics (T0/T0.25/T1/T2, cross-pipeline architecture) defer to the live canonical state in biochem.

## Update Workflow

When shared stack semantics change:
1. Update live canonical state in biochem.
2. Update this file only if clinical-local deltas changed.
3. Keep details in `CLINICAL_BUILD_MODEL.md` and `SUITE_ORCHESTRATION.md`.
