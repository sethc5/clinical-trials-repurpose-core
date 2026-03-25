# Reference Ledger

This folder is the evidence-backed decision ledger for clinical pipeline policy.

Purpose:
- Preserve why we chose specific gates, weights, and selection profiles.
- Keep claims and citations auditable across reruns.
- Avoid undocumented threshold drift.

Structure:
- `decisions/`: decision memos (what changed, why, evidence, tradeoffs)
- `claims/`: claim registry mapping operational claims to sources
- `sources/`: fetched source snapshots (Semantic Scholar bundles, notes)
- `validated_repurposing_pairs.csv`: prior benchmark set

Operational rule:
- Any profile/gate/weight change should update:
  1. a decision memo under `decisions/`
  2. the claim map in `claims/`
  3. source bundles in `sources/` if new literature was used
