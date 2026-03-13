"""
correlation_scanner.py — Cross-candidate findings / pattern detection.

Surfaces systematic patterns across T2 survivors:
  - Mechanism class enrichment
  - Polypharmacology patterns
  - Failed trial rescue patterns
  - Dose gap analysis
  - Evidence type distribution
  - Cross-indication signals

Usage:
    python correlation_scanner.py --config config.yaml
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

from config_schema import PipelineConfig
from db_utils import RepurposingDB

log = logging.getLogger(__name__)


def mechanism_class_enrichment(runs: list[dict], db: RepurposingDB) -> dict:
    """Which drug mechanism classes are overrepresented in T2 survivors?"""
    all_classes: Counter = Counter()
    survivor_classes: Counter = Counter()

    for run in runs:
        drug = db.get_drug(run["drug_id"])
        if not drug:
            continue
        moa = drug.get("mechanism_of_action") or ""
        cls = moa.split()[0] if moa else "unknown"   # crude; T1 will refine
        all_classes[cls] += 1
        if run.get("t2_pass"):
            survivor_classes[cls] += 1

    enrichment = {}
    total_all = sum(all_classes.values()) or 1
    total_survivors = sum(survivor_classes.values()) or 1
    for cls, survivor_count in survivor_classes.items():
        total_count = all_classes[cls]
        enrichment[cls] = {
            "survivor_rate": survivor_count / total_count if total_count else 0,
            "background_rate": total_count / total_all,
            "fold_enrichment": (survivor_count / total_survivors) / (total_count / total_all)
            if total_count
            else 0,
        }
    return dict(sorted(enrichment.items(), key=lambda x: -x[1]["fold_enrichment"]))


def failed_trial_rescue_patterns(runs: list[dict]) -> dict:
    """Distribution of failure reasons among T2 survivors."""
    reason_counts: Counter = Counter()
    for run in runs:
        if run.get("t2_pass") and run.get("t025_failed_trial"):
            reason = run.get("t025_failed_trial_id") or "unknown"
            reason_counts[reason] += 1
    return dict(reason_counts)


def evidence_type_distribution(runs: list[dict], db: RepurposingDB) -> dict:
    """Fraction of T2 evidence that is clinical vs preclinical vs mechanistic."""
    type_counts: Counter = Counter()
    for run in runs:
        if not run.get("t2_pass"):
            continue
        run_id = run.get("run_id")
        if run_id is None:
            continue
        evidence = db.get_evidence_for_run(run_id)
        for ev in evidence:
            type_counts[ev.get("evidence_type", "unknown")] += 1
    total = sum(type_counts.values()) or 1
    return {k: round(v / total, 3) for k, v in type_counts.most_common()}


def cross_indication_signals(runs: list[dict]) -> dict:
    """Drugs that score well across multiple indications simultaneously."""
    drug_indications: dict[str, list[str]] = defaultdict(list)
    for run in runs:
        if run.get("t2_pass"):
            drug_indications[run["drug_id"]].append(run["indication_id"])
    multi = {d: indications for d, indications in drug_indications.items() if len(indications) > 1}
    return dict(sorted(multi.items(), key=lambda x: -len(x[1])))


def run_correlation_scanner(config: PipelineConfig) -> dict[str, Any]:
    db = RepurposingDB(config.output.db_path)
    runs = db.get_runs_at_tier(0)

    findings = {
        "mechanism_class_enrichment": mechanism_class_enrichment(runs, db),
        "failed_trial_rescue_patterns": failed_trial_rescue_patterns(runs),
        "evidence_type_distribution": evidence_type_distribution(runs, db),
        "cross_indication_signals": cross_indication_signals(runs),
    }

    # Persist each as a finding row
    for title, data in findings.items():
        db.insert_finding({
            "title": title,
            "description": json.dumps(data),
            "drug_ids": json.dumps([]),
            "indication_ids": json.dumps([]),
            "statistical_support": "",
        })

    return findings


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Cross-candidate correlation scanner")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    raw = yaml.safe_load(Path(args.config).read_text())
    config = PipelineConfig(**raw)
    findings = run_correlation_scanner(config)
    print(json.dumps(findings, indent=2))


if __name__ == "__main__":
    main()
