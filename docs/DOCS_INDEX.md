# Docs Index And Artifact Map

Purpose: canonical map for where clinical docs live, where artifacts are written, and where cross-repo handoff contracts are defined.

## Canonical Hierarchy

- Shared suite source-of-truth rules:
  - `/home/seth/dev/medicine/biochem-pipeline-core/docs/SUITE_CANONICAL_HIERARCHY.md`
- Shared live pipeline-state canonical source:
  - `/home/seth/dev/medicine/biochem-pipeline-core/docs/PIPELINE_CANONICAL_STATE.md`
- Shared historical architecture snapshot (non-canonical):
  - `/home/seth/dev/medicine/biochem-pipeline-core/docs/PIPELINE_MODEL.md`
- Shared product roots canonical source:
  - `/home/seth/dev/medicine/biochem-pipeline-core/docs/PRODUCT_ROOTS.md`
- Shared package contract checklist:
  - `/home/seth/dev/medicine/biochem-pipeline-core/docs/SUITE_PACKAGE_CONTRACT.md`
- This repo's `docs/PIPELINE_MODEL.md` is a thin local bridge to suite canonical state.

## Session Start Order

1. Read suite canonical hierarchy.
2. Read suite package contract checklist.
3. Read this repo's Start Here list below.

## Start Here

1. `README.md` — scope, tier semantics, and operating intent.
2. `docs/CLINICAL_BUILD_MODEL.md` — reusable build gates/weights, including OTC/vitamin/mineral lane intent.
3. `docs/SUITE_ORCHESTRATION.md` — supervised MVP orchestration flow.
4. `reference/README.md` — evidence-backed decision ledger policy.
5. `docs/COST_OPTIMIZED_COMPUTE_PLAN.md` — compute/cost guardrails.

## Canonical Artifact Locations

| Artifact Type | Canonical Path | Producer | Consumer |
|---|---|---|---|
| Clinical intake DB | `results/repurposing.db` | `scripts/import_biochem_handoff.py`, clinical build scripts | clinical ranking/build flows |
| Imported biochem packages | `suite_handoff/clinical/intake_from_biochem/<run_id>` | `scripts/import_biochem_handoff.py` | clinical build + downstream dossiers |
| Clinical build exports | `results/builds/<build_run_id>.csv` | `scripts/clinical_build.py` | triage/review/routing |
| Clinical intake index row | `suite_handoff/INDEX.md` | import/export scripts | full suite traceability |
| Decision ledger | `reference/decisions/` | operator/manual updates | future sessions |
| Claims registry | `reference/claims/` | operator/manual updates | audit/review |
| Source bundles | `reference/sources/semantic_scholar/` | `scripts/fetch_semantic_scholar_refs.py` | decision + claims updates |

## Reproducibility Commands

Import a biochem package into clinical intake:

```bash
python3 scripts/import_biochem_handoff.py \
  --package /home/seth/dev/medicine/suite_handoff/biochem/t2_validated/<run_id> \
  --suite-root /home/seth/dev/medicine/suite_handoff \
  --db results/repurposing.db
```

Build a clinical cohort from intake:

```bash
python3 scripts/clinical_build.py \
  --db results/repurposing.db \
  --intake-run-id <intake_run_id> \
  --profile-config configs/clinical_build_profiles.yaml \
  --profile provisional_tb
```

Check orchestration queue:

```bash
python3 scripts/suite_orchestrator.py status
```

## Cross-Repo Doc Map

- Biochem canonical map: `/home/seth/dev/medicine/biochem-pipeline-core/docs/DOCS_INDEX.md`
- Biochem integration contract: `/home/seth/dev/medicine/biochem-pipeline-core/docs/INTEGRATED_PIPELINE_MANUAL.md`
- Genomics map: `/home/seth/dev/medicine/genomics_pipeline_core/docs/DOCS_INDEX.md`
- Patent FTO map: `/home/seth/dev/medicine/patent-fto-core/docs/DOCS_INDEX.md`
