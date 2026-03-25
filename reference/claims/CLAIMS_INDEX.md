# Claims Index

## 2026-03-25 — Clinical Build Profiles

| Claim ID | Claim | Source bundle(s) |
|---|---|---|
| `CBP-001` | Staged triage with explicit gates can reduce false-priority candidates and improve portfolio focus in repurposing workflows. | `reference/sources/semantic_scholar/20260325_200514_clinical_build_profiles_curated_candidates.md`; `reference/sources/semantic_scholar/2026-03-25_clinical_build_profiles_curated.md` |
| `CBP-002` | Multi-factor scoring (mechanistic signal + translational signal + uncertainty/risk controls) is preferable to single-metric ranking. | `reference/sources/semantic_scholar/20260325_200514_clinical_build_profiles_curated_candidates.md`; `reference/sources/semantic_scholar/2026-03-25_clinical_build_profiles_curated.md` |
| `CBP-003` | Numerical thresholds should be calibrated to target-specific score distributions and updated as new runs complete. | `reference/decisions/2026-03-25_clinical_build_profiles_v1.md` |
| `CBP-004` | Evidence hierarchy and trial-quality weighting should influence strict profile behavior for downstream clinical work products. | `reference/sources/semantic_scholar/20260325_200514_clinical_build_profiles_curated_candidates.md`; `reference/sources/semantic_scholar/2026-03-25_clinical_build_profiles_curated.md` |

## 2026-03-25 — Suite Compute Policy (Genomics-First)

| Claim ID | Claim | Source bundle(s) |
|---|---|---|
| `SCP-001` | RunPod serverless/Flash pricing is per-second and suitable for cost-controlled burst workloads with explicit idle/worker controls. | `reference/sources/web/2026-03-25_runpod_openrouter_cost.md` |
| `SCP-002` | Flash follows serverless pricing semantics, so backend choice should be workload-shape driven (short request jobs vs long stateful jobs). | `reference/sources/web/2026-03-25_runpod_openrouter_cost.md` |
| `SCP-003` | OpenRouter supports provider sort/fallback controls that can enforce price-priority routing when needed. | `reference/sources/web/2026-03-25_runpod_openrouter_cost.md` |
| `SCP-004` | OpenRouter supports request-level data policy controls (`data_collection`, `zdr`) that can be encoded as reusable profiles. | `reference/sources/web/2026-03-25_runpod_openrouter_cost.md` |
| `SCP-005` | A staged migration (genomics-first pilot, biochem later) reduces disruption risk while still improving cost efficiency. | `reference/decisions/2026-03-25_suite_compute_policy_genomics_first.md` |
