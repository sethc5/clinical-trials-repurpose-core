# Suite Orchestration (Supervised MVP)

## Goal
Automate the full genomics -> biochem -> clinical flow with tight loops and low fragility.

This MVP is intentionally supervised:
- one stage per run cycle
- persistent queue DB
- explicit review checkpoints at high-risk transitions
- dry-run default for safe rollout

## Components
- Orchestrator CLI: `scripts/suite_orchestrator.py`
- Runtime config: `configs/suite_orchestrator.yaml`
- Backlog template: `configs/suite_backlog.example.yaml`
- Queue DB (runtime): `results/orchestrator.db`

## Supported Job Types
1. `genomics_to_biochem`
- Stage: genomics handoff export
- Checkpoint: review generated target package

2. `biochem_to_clinical`
- Stage: finalize biochem + export package
- Checkpoint: review export before clinical ingest
- Stage: discover package
- Stage: clinical import
- Stage: clinical provisional build
- Checkpoint: review before strict build
- Stage: clinical strict build

## Command Flow
Initialize:
```bash
python3 scripts/suite_orchestrator.py init
```

Enqueue:
```bash
python3 scripts/suite_orchestrator.py enqueue \
  --backlog configs/suite_backlog.example.yaml
```

Status:
```bash
python3 scripts/suite_orchestrator.py status
```

Run one stage in dry-run mode:
```bash
python3 scripts/suite_orchestrator.py run-once
```

Run one stage for real:
```bash
python3 scripts/suite_orchestrator.py run-once --execute
```

Run one stage with a runtime profile override (for backend-specific command templates):
```bash
python3 scripts/suite_orchestrator.py --compute-profile hetzner run-once --execute
```

Approve checkpoint:
```bash
python3 scripts/suite_orchestrator.py approve --job-id tb_inha_biochem_to_clinical
```

Inspect events:
```bash
python3 scripts/suite_orchestrator.py events --job-id tb_inha_biochem_to_clinical
```

## Reliability Rules
- Keep `run-once --execute` in cron/loop only after dry-run validation.
- Keep approval checkpoints until >3 clean cycles.
- Keep stage commands idempotent where possible.
- Record all policy changes in `reference/`.

## Compute Policy Hooks
Runtime config keeps command templates centralized so compute backends can change without rewriting orchestrator logic:
- local execution (default)
- Hetzner command wrappers
- RunPod profile stubs (activate once serverless wrappers are implemented)

See `docs/COST_OPTIMIZED_COMPUTE_PLAN.md` for the low-cost genomics-first rollout and OpenRouter budget policy.
