"""
cross_indication_analysis.py — Find drugs that score positively across multiple
independent indications (promising broad repurposing candidates).

Joins the runs table across indication IDs and surfaces drugs that reach T2
for ≥2 distinct indications — a strong signal of target versatility.

Usage:
    python cross_indication_analysis.py --db results/repurposing.db
    python cross_indication_analysis.py --db results/repurposing.db --tier t2 --min-indications 2
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def load_multi_indication_drugs(
    db_path: str,
    tier: str = "t2",
    min_indications: int = 2,
) -> dict[str, list[dict]]:
    """
    Return a mapping of drug_id → [run_rows] for drugs that survive the
    specified tier for at least *min_indications* distinct indications.

    Args:
        db_path: Path to the SQLite database.
        tier: Minimum tier reached ("t0", "t025", "t1", "t2").
        min_indications: Minimum number of distinct indications required.

    Returns:
        {drug_id: [run_dict, ...]} for qualifying drugs.
    """
    tier_col_map = {
        "t0": "t0_pass",
        "t025": "t025_pass",
        "t1": "t1_pass",
        "t2": "t2_pass",
    }
    if tier not in tier_col_map:
        raise ValueError(f"Unknown tier {tier!r}; choose from {list(tier_col_map)}")
    col = tier_col_map[tier]

    with _connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT r.drug_id, r.indication_id, r.composite_score,
                   r.t0_pass, r.t025_pass, r.t1_pass, r.t2_pass,
                   r.t1_evidence_score, r.t1_mechanistic_score, r.t1_safety_score,
                   d.name as drug_name, i.name as indication_name
            FROM runs r
            LEFT JOIN drugs d ON r.drug_id = d.drug_id
            LEFT JOIN indications i ON r.indication_id = i.indication_id
            WHERE r.{col} = 1
            ORDER BY r.drug_id, r.composite_score DESC
            """
        ).fetchall()

    by_drug: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_drug[row["drug_id"]].append(dict(row))

    return {
        drug_id: runs
        for drug_id, runs in by_drug.items()
        if len(runs) >= min_indications
    }


def analyze(
    multi_indication_drugs: dict[str, list[dict]],
) -> list[dict]:
    """
    Build summary records for multi-indication drugs.

    Returns a list sorted by number of indications (desc), then mean composite score.
    """
    results = []
    for drug_id, runs in multi_indication_drugs.items():
        indications = [r["indication_name"] or r["indication_id"] for r in runs]
        scores = [r["composite_score"] or 0.0 for r in runs]
        mean_score = sum(scores) / len(scores) if scores else 0.0
        best_run = max(runs, key=lambda r: r.get("composite_score") or 0.0)

        results.append(
            {
                "drug_id": drug_id,
                "drug_name": best_run.get("drug_name") or drug_id,
                "n_indications": len(runs),
                "indications": indications,
                "mean_composite_score": round(mean_score, 4),
                "best_composite_score": round(max(scores), 4),
                "best_indication": best_run.get("indication_name") or best_run.get("indication_id"),
                "runs": runs,
            }
        )

    results.sort(key=lambda x: (-x["n_indications"], -x["mean_composite_score"]))
    return results


def print_report(results: list[dict]) -> None:
    if not results:
        print("No multi-indication candidates found.")
        return

    print(f"\n{'='*70}")
    print(f"  CROSS-INDICATION REPURPOSING CANDIDATES ({len(results)} drugs)")
    print(f"{'='*70}\n")

    for r in results:
        print(f"  {r['drug_name']} ({r['drug_id']})")
        print(f"    Indications ({r['n_indications']}): {', '.join(r['indications'])}")
        print(
            f"    Scores — mean: {r['mean_composite_score']:.3f}, "
            f"best: {r['best_composite_score']:.3f} ({r['best_indication']})"
        )
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Cross-indication repurposing analysis")
    parser.add_argument("--db", required=True, help="Path to repurposing SQLite database")
    parser.add_argument(
        "--tier",
        default="t2",
        choices=["t0", "t025", "t1", "t2"],
        help="Minimum tier that must be reached (default: t2)",
    )
    parser.add_argument(
        "--min-indications",
        type=int,
        default=2,
        dest="min_indications",
        help="Minimum number of indications (default: 2)",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--out", help="Write JSON results to this file")
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"Database not found: {args.db}")
        raise SystemExit(1)

    multi = load_multi_indication_drugs(args.db, tier=args.tier, min_indications=args.min_indications)
    results = analyze(multi)

    if args.json or args.out:
        # Strip verbose run data for JSON output
        slim = [{k: v for k, v in r.items() if k != "runs"} for r in results]
        out_str = json.dumps(slim, indent=2)
        if args.out:
            Path(args.out).write_text(out_str)
            print(f"Results written to {args.out}")
        else:
            print(out_str)
    else:
        print_report(results)


if __name__ == "__main__":
    main()
