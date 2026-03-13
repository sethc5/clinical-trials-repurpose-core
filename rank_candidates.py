"""
rank_candidates.py — Composite scoring and final ranking of T2 survivors.

Produces a ranked CSV and console summary of top repurposing candidates.

Usage:
    python rank_candidates.py --config config.yaml --top 30
"""

from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path

import yaml

from config_schema import PipelineConfig
from db_utils import RepurposingDB

log = logging.getLogger(__name__)

WEIGHT_EVIDENCE = 0.35
WEIGHT_MECHANISTIC = 0.30
WEIGHT_SAFETY = 0.20
WEIGHT_NOVELTY = 0.15


def composite_score(run: dict) -> float:
    ev = run.get("t1_evidence_score") or 0.0
    mech = run.get("t1_mechanistic_score") or 0.0
    safety = run.get("t1_safety_score") or 0.0
    novelty = run.get("t2_novelty") or 0.0
    return (
        WEIGHT_EVIDENCE * ev
        + WEIGHT_MECHANISTIC * mech
        + WEIGHT_SAFETY * safety
        + WEIGHT_NOVELTY * novelty
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--top", type=int, default=30)
    args = parser.parse_args()

    raw = yaml.safe_load(Path(args.config).read_text())
    config = PipelineConfig(**raw)
    db = RepurposingDB(config.output.db_path)

    runs = db.get_runs_at_tier(2)
    t2_runs = [r for r in runs if r.get("t2_pass")]

    for run in t2_runs:
        run["composite_score"] = composite_score(run)
        db.upsert_run(run)

    ranked = sorted(t2_runs, key=lambda r: -r["composite_score"])[:args.top]

    # Print summary
    print(f"\nTop {len(ranked)} repurposing candidates:\n")
    print(f"{'Rank':<5} {'Drug':<20} {'Indication':<25} {'Score':<8} {'Confidence'}")
    print("-" * 75)
    for i, run in enumerate(ranked, 1):
        drug = db.get_drug(run["drug_id"])
        ind = db.get_indication(run["indication_id"])
        drug_name = drug["name"] if drug else run["drug_id"]
        ind_name = ind["name"] if ind else run["indication_id"]
        score = run["composite_score"]
        conf = run.get("t2_confidence") or 0.0
        print(f"{i:<5} {drug_name:<20} {ind_name:<25} {score:<8.3f} {conf:.3f}")

    # Export CSV
    results_dir = Path(config.output.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    out_csv = results_dir / "ranked_candidates.csv"

    keys = ["drug_id", "indication_id", "composite_score", "t2_confidence",
            "t1_evidence_score", "t1_mechanistic_score", "t1_safety_score", "t2_novelty"]
    with out_csv.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(ranked)

    log.info(f"Results written to {out_csv}")


if __name__ == "__main__":
    main()
