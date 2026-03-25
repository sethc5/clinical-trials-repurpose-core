#!/usr/bin/env python3
"""
Reusable clinical candidate build engine with profile knobs/sliders.

This script turns one imported biochem intake run into a reusable clinical
build cohort using configurable gates and weighted scoring profiles.

Examples:
  python3 scripts/clinical_build.py \
    --db results/repurposing.db \
    --intake-run-id 20260325_1409_clinical_intake_tb_inha_top25_t2 \
    --profile-config configs/clinical_build_profiles.yaml \
    --profile provisional_tb

  python3 scripts/clinical_build.py \
    --db results/repurposing.db \
    --list-build-run 20260325_2010_provisional_tb_tb_inha_top25_t2 \
    --included-only
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from db_utils import RepurposingDB


DEFAULT_DB = Path("results/repurposing.db")
DEFAULT_PROFILE_CONFIG = Path("configs/clinical_build_profiles.yaml")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _to_float(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _to_int(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _normalize(value: float, low: float, high: float, higher_is_better: bool) -> float:
    if high <= low:
        return 0.5
    x = (value - low) / (high - low)
    x = max(0.0, min(1.0, x))
    return x if higher_is_better else 1.0 - x


def _first_non_none(values: list[Any]) -> Any | None:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _extract_candidate_metrics(candidate: dict) -> dict[str, Any]:
    src = candidate.get("source_row_json") or {}
    t1_score = _to_float(
        _first_non_none([candidate.get("score_t1"), src.get("score_t1"), src.get("t1_score")])
    )
    t2_score = _to_float(
        _first_non_none([candidate.get("score_t2"), src.get("score_t2"), src.get("t2_score")])
    )
    rank_t1 = _to_int(
        _first_non_none([candidate.get("rank_t1"), src.get("rank_t1"), src.get("t1_rank")])
    )
    rank_t2 = _to_int(
        _first_non_none([candidate.get("rank_t2"), src.get("rank_t2"), src.get("t2_rank")])
    )
    t2_rmsd = _to_float(src.get("t2_rmsd"))
    t2_persistence = _to_float(src.get("t2_persistence"))

    return {
        "intake_run_id": candidate.get("intake_run_id"),
        "compound_id": candidate.get("compound_id"),
        "target_id": candidate.get("target_id"),
        "smiles": candidate.get("smiles"),
        "t1_score": t1_score,
        "t2_score": t2_score,
        "rank_t1": rank_t1,
        "rank_t2": rank_t2,
        "t2_rmsd": t2_rmsd,
        "t2_persistence": t2_persistence,
        "source_row_json": src,
    }


def _load_profile(path: Path, profile_name: str) -> tuple[str, dict]:
    if not path.exists():
        raise ValueError(f"profile config not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    profiles = raw.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError(f"profile config missing profiles map: {path}")
    if profile_name not in profiles:
        raise ValueError(f"profile {profile_name!r} not found in {path}")
    version = str(raw.get("version", "1.0"))
    profile = profiles[profile_name] or {}
    if not isinstance(profile, dict):
        raise ValueError(f"profile {profile_name!r} must be a mapping")
    return version, profile


def _collect_bounds(candidates: list[dict], scoring: dict) -> dict[str, tuple[float, float]]:
    ranges = scoring.get("ranges") or {}

    def _vals(key: str) -> list[float]:
        out: list[float] = []
        for candidate in candidates:
            value = _to_float(candidate.get(key))
            if value is not None and not math.isnan(value):
                out.append(value)
        return out

    def _bound(metric: str, fallback_low: float, fallback_high: float) -> tuple[float, float]:
        range_low = _to_float(ranges.get(f"{metric}_min"))
        range_high = _to_float(ranges.get(f"{metric}_max"))
        if range_low is not None and range_high is not None:
            return (min(range_low, range_high), max(range_low, range_high))
        values = _vals(metric)
        if values:
            return (min(values), max(values))
        return (fallback_low, fallback_high)

    return {
        "t1_score": _bound("t1_score", -12.0, -8.0),
        "t2_score": _bound("t2_score", 0.0, 1.0),
        "t2_persistence": _bound("t2_persistence", 0.0, 1.0),
        "t2_rmsd": _bound("t2_rmsd", 2.0, 12.0),
        "rank_t1": _bound("rank_t1", 1.0, 200.0),
    }


def _gate_candidate(metrics: dict, gates: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    required_targets = gates.get("required_targets") or []
    if required_targets and metrics.get("target_id") not in required_targets:
        reasons.append("target_not_in_required_targets")

    max_t1_score = _to_float(gates.get("max_t1_score"))
    if max_t1_score is not None:
        t1_score = _to_float(metrics.get("t1_score"))
        if t1_score is None or t1_score > max_t1_score:
            reasons.append("t1_score_gate")

    max_rank_t1 = _to_int(gates.get("max_rank_t1"))
    if max_rank_t1 is not None:
        rank_t1 = _to_int(metrics.get("rank_t1"))
        if rank_t1 is None or rank_t1 > max_rank_t1:
            reasons.append("rank_t1_gate")

    max_rank_t2 = _to_int(gates.get("max_rank_t2"))
    if max_rank_t2 is not None:
        rank_t2 = _to_int(metrics.get("rank_t2"))
        if rank_t2 is None or rank_t2 > max_rank_t2:
            reasons.append("rank_t2_gate")

    require_t2_metrics = bool(gates.get("require_t2_metrics", False))
    t2_rmsd = _to_float(metrics.get("t2_rmsd"))
    t2_persistence = _to_float(metrics.get("t2_persistence"))
    if require_t2_metrics and (t2_rmsd is None or t2_persistence is None):
        reasons.append("missing_t2_metrics")

    max_t2_rmsd = _to_float(gates.get("max_t2_rmsd"))
    if max_t2_rmsd is not None and t2_rmsd is not None and t2_rmsd > max_t2_rmsd:
        reasons.append("t2_rmsd_gate")

    min_t2_persistence = _to_float(gates.get("min_t2_persistence"))
    if min_t2_persistence is not None and t2_persistence is not None and t2_persistence < min_t2_persistence:
        reasons.append("t2_persistence_gate")

    min_t2_score = _to_float(gates.get("min_t2_score"))
    if min_t2_score is not None:
        t2_score = _to_float(metrics.get("t2_score"))
        if t2_score is None or t2_score < min_t2_score:
            reasons.append("t2_score_gate")

    return (len(reasons) == 0), reasons


def _score_candidate(metrics: dict, scoring: dict, bounds: dict[str, tuple[float, float]]) -> tuple[float, dict[str, float]]:
    weights = scoring.get("weights") or {}
    defaults = scoring.get("defaults") or {}

    metric_specs = {
        "t1_score": {"higher_is_better": False},
        "t2_score": {"higher_is_better": True},
        "t2_persistence": {"higher_is_better": True},
        "t2_rmsd": {"higher_is_better": False},
        "rank_t1": {"higher_is_better": False},
    }

    total_weight = 0.0
    weighted_sum = 0.0
    components: dict[str, float] = {}

    for metric, spec in metric_specs.items():
        weight = _to_float(weights.get(metric)) or 0.0
        if weight <= 0.0:
            continue
        raw_value = _to_float(metrics.get(metric))
        if raw_value is None:
            raw_value = _to_float(defaults.get(metric))
        if raw_value is None:
            component = 0.0
        else:
            low, high = bounds[metric]
            component = _normalize(raw_value, low, high, spec["higher_is_better"])
        components[metric] = component
        weighted_sum += weight * component
        total_weight += weight

    score = 0.0 if total_weight <= 0 else weighted_sum / total_weight
    return score, components


def build_clinical_run(
    db: RepurposingDB,
    intake_run_id: str,
    profile_name: str,
    profile_version: str,
    profile: dict,
    build_run_id: str,
    notes: str = "",
) -> dict[str, Any]:
    candidates_raw = db.list_biochem_intake_candidates(intake_run_id=intake_run_id)
    if not candidates_raw:
        raise ValueError(f"no intake candidates found for intake_run_id={intake_run_id}")

    candidates = [_extract_candidate_metrics(c) for c in candidates_raw]
    gates = profile.get("gates") or {}
    scoring = profile.get("scoring") or {}
    selection = profile.get("selection") or {}
    top_k = _to_int(selection.get("top_k")) or len(candidates)
    include_gate_failures = bool(selection.get("include_gate_failures", False))

    bounds = _collect_bounds(candidates, scoring=scoring)
    evaluated: list[dict[str, Any]] = []
    for candidate in candidates:
        gate_pass, gate_reasons = _gate_candidate(candidate, gates=gates)
        score, components = _score_candidate(candidate, scoring=scoring, bounds=bounds)
        evaluated.append(
            {
                **candidate,
                "gate_pass": gate_pass,
                "gate_reasons": gate_reasons,
                "score": score,
                "score_components": components,
            }
        )

    if include_gate_failures:
        inclusion_pool = sorted(evaluated, key=lambda row: row["score"], reverse=True)
    else:
        inclusion_pool = sorted(
            [row for row in evaluated if row["gate_pass"]],
            key=lambda row: row["score"],
            reverse=True,
        )

    included_keys = {(row["compound_id"], row["target_id"]) for row in inclusion_pool[:top_k]}

    persisted_rows: list[dict[str, Any]] = []
    included_rank = 0
    for row in sorted(evaluated, key=lambda r: r["score"], reverse=True):
        key = (row["compound_id"], row["target_id"])
        included = key in included_keys
        if included:
            included_rank += 1
            include_reason = "selected"
        elif row["gate_pass"]:
            include_reason = "below_top_k"
        else:
            include_reason = f"gate_fail:{','.join(row['gate_reasons'])}"

        persisted_rows.append(
            {
                "intake_run_id": intake_run_id,
                "compound_id": row["compound_id"],
                "target_id": row["target_id"],
                "included": included,
                "include_reason": include_reason,
                "score": row["score"],
                "rank_included": included_rank if included else None,
                "metrics_json": {
                    "t1_score": row.get("t1_score"),
                    "t2_score": row.get("t2_score"),
                    "rank_t1": row.get("rank_t1"),
                    "rank_t2": row.get("rank_t2"),
                    "t2_rmsd": row.get("t2_rmsd"),
                    "t2_persistence": row.get("t2_persistence"),
                    "gate_pass": row["gate_pass"],
                    "gate_reasons": row["gate_reasons"],
                    "score_components": row["score_components"],
                },
            }
        )

    included_count = sum(1 for row in persisted_rows if row["included"])
    db.upsert_clinical_build_run(
        {
            "build_run_id": build_run_id,
            "intake_run_id": intake_run_id,
            "profile_name": profile_name,
            "profile_version": profile_version,
            "profile_json": profile,
            "created_utc": _utc_now(),
            "notes": notes,
            "total_candidates": len(persisted_rows),
            "included_candidates": included_count,
        }
    )
    db.upsert_clinical_build_candidates(build_run_id=build_run_id, candidates=persisted_rows)

    return {
        "build_run_id": build_run_id,
        "intake_run_id": intake_run_id,
        "profile_name": profile_name,
        "total_candidates": len(persisted_rows),
        "included_candidates": included_count,
        "rows": persisted_rows,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "build_run_id",
        "intake_run_id",
        "compound_id",
        "target_id",
        "included",
        "rank_included",
        "score",
        "include_reason",
        "metrics_json",
    ]
    import csv

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "build_run_id": row["build_run_id"],
                    "intake_run_id": row["intake_run_id"],
                    "compound_id": row["compound_id"],
                    "target_id": row["target_id"],
                    "included": int(bool(row["included"])),
                    "rank_included": row.get("rank_included"),
                    "score": f"{float(row['score']):.6f}" if row.get("score") is not None else "",
                    "include_reason": row.get("include_reason") or "",
                    "metrics_json": json.dumps(row.get("metrics_json") or {}, separators=(",", ":")),
                }
            )


def _list_build_run(db: RepurposingDB, build_run_id: str, included_only: bool, limit: int | None) -> int:
    rows = db.list_clinical_build_candidates(
        build_run_id=build_run_id,
        included_only=included_only,
        limit=limit,
    )
    if not rows:
        print(f"No build candidates found for build_run_id={build_run_id}")
        return 0

    print("build_run_id\tcompound_id\ttarget_id\tincluded\trank_included\tscore\treason")
    for row in rows:
        print(
            f"{row['build_run_id']}\t{row['compound_id']}\t{row['target_id']}\t"
            f"{int(bool(row['included']))}\t{row.get('rank_included')}\t"
            f"{row.get('score')}\t{row.get('include_reason')}"
        )
    return len(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description="Reusable clinical build cohorts from intake candidates")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to clinical SQLite DB")
    ap.add_argument("--profile-config", type=Path, default=DEFAULT_PROFILE_CONFIG)
    ap.add_argument("--profile", type=str, default="provisional_tb")
    ap.add_argument("--intake-run-id", type=str, default=None)
    ap.add_argument("--build-run-id", type=str, default=None)
    ap.add_argument("--notes", type=str, default="")
    ap.add_argument("--out-csv", type=Path, default=None, help="Optional export CSV path")
    ap.add_argument("--list-build-run", type=str, default=None)
    ap.add_argument("--included-only", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    db = RepurposingDB(args.db)
    db.init_schema()

    if args.list_build_run:
        _list_build_run(db, args.list_build_run, included_only=args.included_only, limit=args.limit)
        return

    if not args.intake_run_id:
        raise SystemExit("--intake-run-id is required unless --list-build-run is used.")

    profile_version, profile = _load_profile(args.profile_config, args.profile)
    build_run_id = args.build_run_id or datetime.now(timezone.utc).strftime(
        f"%Y%m%d_%H%M_{args.profile}_{args.intake_run_id}"
    )

    result = build_clinical_run(
        db=db,
        intake_run_id=args.intake_run_id,
        profile_name=args.profile,
        profile_version=profile_version,
        profile=profile,
        build_run_id=build_run_id,
        notes=args.notes,
    )

    rows = db.list_clinical_build_candidates(build_run_id=build_run_id)
    csv_path = args.out_csv
    if csv_path is None:
        csv_path = Path("results") / "builds" / f"{build_run_id}.csv"
    csv_rows = [{**row, "build_run_id": build_run_id} for row in rows]
    _write_csv(csv_path, csv_rows)

    print(
        f"Build run complete: build_run_id={result['build_run_id']} "
        f"included={result['included_candidates']}/{result['total_candidates']} "
        f"csv={csv_path}"
    )


if __name__ == "__main__":
    main()
