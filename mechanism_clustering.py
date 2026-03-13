"""
mechanism_clustering.py — Cluster T2 candidates by mechanism class.

Groups repurposing candidates into mechanism clusters so that:
- Reviewers can assess structural/mechanistic diversity
- Over-reliance on a single mechanism class is surfaced

Usage:
    python mechanism_clustering.py --config config.yaml
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from pathlib import Path

import yaml

from config_schema import PipelineConfig
from db_utils import RepurposingDB

log = logging.getLogger(__name__)


def cluster_by_mechanism(runs: list[dict], db: RepurposingDB) -> dict[str, list[str]]:
    """Return {mechanism_class: [drug_id, ...]}."""
    clusters: dict[str, list[str]] = defaultdict(list)
    for run in runs:
        if not run.get("t2_pass"):
            continue
        drug = db.get_drug(run["drug_id"])
        if not drug:
            continue
        moa = (drug.get("mechanism_of_action") or "unknown").lower()
        # Crude but serviceable first-pass classification
        if "kinase" in moa:
            cls = "kinase_inhibitor"
        elif "mtor" in moa or "rapamycin" in moa:
            cls = "mtor_inhibitor"
        elif "hdac" in moa:
            cls = "hdac_inhibitor"
        elif "ampk" in moa or "metformin" in moa:
            cls = "ampk_activator"
        elif "sirtuin" in moa or "sir2" in moa:
            cls = "sirtuin_activator"
        elif "nad" in moa or "nampt" in moa:
            cls = "nad_pathway"
        elif "senolytic" in moa or "bcl-2" in moa or "bcl2" in moa:
            cls = "senolytic"
        elif "anti-inflam" in moa or "nsaid" in moa or "cox" in moa:
            cls = "anti_inflammatory"
        else:
            cls = "other"
        clusters[cls].append(run["drug_id"])
    return dict(clusters)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Cluster candidates by mechanism class")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    raw = yaml.safe_load(Path(args.config).read_text())
    config = PipelineConfig(**raw)
    db = RepurposingDB(config.output.db_path)
    runs = db.get_runs_at_tier(2)
    clusters = cluster_by_mechanism(runs, db)

    print("\nMechanism clusters (T2 survivors):")
    for cls, drug_ids in sorted(clusters.items(), key=lambda x: -len(x[1])):
        print(f"  {cls}: {len(drug_ids)} drugs — {drug_ids[:5]}")

    out = Path(config.output.results_dir) / "mechanism_clusters.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(clusters, indent=2))
    log.info(f"Clusters written to {out}")


if __name__ == "__main__":
    main()
