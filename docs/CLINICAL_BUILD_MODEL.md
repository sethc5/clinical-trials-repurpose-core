# Clinical Build Model (Reusable Knobs/Sliders)

## Purpose
Create reusable clinical cohorts from biochem intake packages without rewriting per-candidate logic.

The model separates:
- Reusable engine logic (gates + weighted scoring + selection)
- Per-candidate evidence state (metrics from intake row)
- Build profile presets (provisional vs strict)

This lets us generate:
- Early exploratory build sets
- Final handoff-quality build sets
- Deterministic reruns as metrics change

## Inputs
- `biochem_intake_runs`: one imported intake run
- `biochem_intake_candidates`: candidate rows with normalized fields and `source_row_json`
- Profile YAML: `configs/clinical_build_profiles.yaml`

## Knobs / Sliders
Profile knobs live in YAML and are versioned:

1. Gates (`profiles.<name>.gates`)
- `max_t1_score`
- `max_rank_t1`
- `max_rank_t2`
- `max_t2_rmsd`
- `min_t2_persistence`
- `min_t2_score`
- `require_t2_metrics`
- `required_targets`

2. Scoring (`profiles.<name>.scoring`)
- Weighted components: `t1_score`, `t2_score`, `t2_persistence`, `t2_rmsd`, `rank_t1`
- Optional normalization ranges per metric
- Metric defaults for missing values

3. Selection (`profiles.<name>.selection`)
- `top_k`
- `include_gate_failures`

## Output Contract
Each build run writes to DB:
- `clinical_build_runs` (profile snapshot + counts)
- `clinical_build_candidates` (included flag, reason, rank, score, metric breakdown)

And exports a CSV in:
- `results/builds/<build_run_id>.csv`

## Why This Is Reusable
- Same engine for all compounds/targets/intake runs
- Different “policy” comes from profile YAML only
- Can run provisional now and strict later against same intake lineage
- Supports delta reruns by changing only profile or intake id

## CLI
Build:
```bash
python3 scripts/clinical_build.py \
  --db results/repurposing.db \
  --intake-run-id <intake_run_id> \
  --profile-config configs/clinical_build_profiles.yaml \
  --profile provisional_tb
```

List:
```bash
python3 scripts/clinical_build.py \
  --db results/repurposing.db \
  --list-build-run <build_run_id> \
  --included-only
```
