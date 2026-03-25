# Curated Evidence Note — Clinical Build Profiles v1

- Date (UTC): `2026-03-25`
- Source bundle: `20260325_200514_clinical_build_profiles_curated_candidates.*`
- Purpose: Support policy choices in `configs/clinical_build_profiles.yaml`

## Inclusion Rule
Selected papers that support:
1. staged repurposing triage
2. multi-signal ranking (network/transcriptomic + evidence)
3. evidence-quality-aware downstream strictness

## Selected Core References

1. Pushpakom et al., 2018 (Nat Rev Drug Discov), DOI `10.1038/nrd.2018.168`
- Justifies drug-repurposing bottlenecks and need for disciplined screening/translation strategy.

2. Himmelstein et al., 2017 (eLife preprint lineage), DOI `10.7554/eLife.26726`
- Supports integrated multi-source network evidence for repurposing prioritization.

3. Corsello et al., 2020 (Nature Cancer), DOI `10.1038/s43018-019-0018-6`
- Supports systematic viability profiling and quantitative prioritization workflows.

4. Lamb et al., 2006 (Science), DOI `10.1126/science.1132939`
- Core rationale for transcriptomic signature matching in repurposing.

5. Kim et al., 2018 (JKMS), DOI `10.3346/jkms.2018.33.e213`
- Supports role separation of RCT evidence and real-world evidence in clinical decisions.

6. O'Connor et al., 2011 (Current Allergy Asthma Rep), DOI `10.1007/s11882-011-0222-7`
- Supports evidence hierarchy interpretation and comparative effectiveness framing.

## Relevance to Current Profiles
- `provisional_tb`: permits broader candidate inclusion while T2 recalibration is in-flight.
- `strict_tb`: requires stronger/complete metrics before downstream clinical artifacts.

## Note on Numeric Thresholds
The exact numeric cutoffs (`max_t1_score`, `max_t2_rmsd`, `min_t2_persistence`) are not directly copied from literature; they are target-calibrated from current TB run distributions and should be re-locked after Stage B reruns complete.
