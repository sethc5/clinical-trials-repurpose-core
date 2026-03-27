#!/usr/bin/env python3
"""
Import a biochem candidate package into clinical intake lane.

This script validates and copies the package into
suite_handoff/clinical/intake_from_biochem with an import receipt,
then writes the intake metadata + candidates to clinical SQLite staging tables.

Example:
  python3 scripts/import_biochem_handoff.py \
    --package /home/seth/dev/medicine/suite_handoff/biochem/t2_validated/<run_id>

  python3 scripts/import_biochem_handoff.py \
    --db results/repurposing.db \
    --list-intake-run 20260325_1409_clinical_intake_tb_focus
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from db_utils import RepurposingDB


DEFAULT_SUITE_ROOT = Path("/home/seth/dev/medicine/suite_handoff")
DEFAULT_DB = Path("results/repurposing.db")
INDEX_HEADER = (
    "| logged_utc | domain | state | run_id | package_path | source_repo | source_commit | records | notes |\n"
    "|---|---|---|---|---|---|---|---:|---|\n"
)
REQUIRED_CANDIDATE_COLUMNS = ("compound_id", "smiles", "target_id")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _append_index(
    suite_root: Path,
    run_id: str,
    package_path: Path,
    source_repo: str,
    source_commit: str,
    records: int,
    notes: str = "",
) -> None:
    index_path = suite_root / "INDEX.md"
    if not index_path.exists():
        index_path.write_text(
            "# Suite Handoff Index\n\n"
            "Auto-appended by handoff scripts.\n\n"
            + INDEX_HEADER,
            encoding="utf-8",
        )
    content = index_path.read_text(encoding="utf-8")
    if "| logged_utc | domain | state | run_id |" not in content:
        index_path.write_text(content + "\n" + INDEX_HEADER, encoding="utf-8")
        content = index_path.read_text(encoding="utf-8")

    safe_notes = notes.replace("|", "/")
    row_marker = f"| clinical | intake_from_biochem | {run_id} | {package_path} |"
    if row_marker in content:
        return

    row = (
        f"| {_utc_now()} | clinical | intake_from_biochem | {run_id} | {package_path} | "
        f"{source_repo} | {source_commit} | {records} | {safe_notes} |\n"
    )
    with index_path.open("a", encoding="utf-8") as f:
        f.write(row)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _to_optional_float(raw: str | None) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _to_optional_int(raw: str | None) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _read_candidates(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        if r.fieldnames is None:
            raise ValueError("candidates.csv has no header.")
        missing = [c for c in REQUIRED_CANDIDATE_COLUMNS if c not in r.fieldnames]
        if missing:
            raise ValueError(f"candidates.csv missing required columns: {missing}")
        candidates = []
        for idx, row in enumerate(r, start=2):
            normalized = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
            blank = [c for c in REQUIRED_CANDIDATE_COLUMNS if not normalized.get(c)]
            if blank:
                raise ValueError(f"candidates.csv row {idx} missing required values: {blank}")

            candidates.append(
                {
                    "compound_id": normalized["compound_id"],
                    "smiles": normalized["smiles"],
                    "target_id": normalized["target_id"],
                    "score_t1": _to_optional_float(normalized.get("score_t1") or normalized.get("t1_score")),
                    "score_t2": _to_optional_float(normalized.get("score_t2") or normalized.get("t2_score")),
                    "rank_t1": _to_optional_int(normalized.get("rank_t1") or normalized.get("t1_rank")),
                    "rank_t2": _to_optional_int(normalized.get("rank_t2") or normalized.get("t2_rank")),
                    "source_row_json": normalized,
                }
            )
        _backfill_missing_ranks(candidates)
        return candidates


def _backfill_missing_ranks(candidates: list[dict]) -> None:
    """Backfill rank fields when legacy exports omit explicit rank columns."""
    ranked_t1 = sorted(
        [c for c in candidates if c.get("score_t1") is not None],
        key=lambda c: (float(c["score_t1"]), c["compound_id"]),
    )
    for idx, candidate in enumerate(ranked_t1, start=1):
        if candidate.get("rank_t1") is None:
            candidate["rank_t1"] = idx


def import_package(
    package: Path,
    suite_root: Path,
    db_path: Path,
    run_id: str | None = None,
    notes: str = "",
) -> tuple[str, Path, int]:
    src = package.resolve()
    if not src.is_dir():
        raise ValueError(f"Package directory not found: {src}")

    manifest_path = src / "manifest.json"
    candidates_path = src / "candidates.csv"
    provenance_path = src / "provenance.json"
    for p in (manifest_path, candidates_path, provenance_path):
        if not p.exists():
            raise ValueError(f"Required file missing: {p}")

    manifest = _load_json(manifest_path)
    if manifest.get("artifact_type") != "candidate_package":
        raise ValueError(f"Unsupported artifact_type: {manifest.get('artifact_type')!r}")

    provenance = _load_json(provenance_path)
    candidates = _read_candidates(candidates_path)
    n_rows = len(candidates)

    source_run_id = manifest.get("run_id", src.name)
    source_repo = (
        manifest.get("source_repo")
        or provenance.get("source_repo")
        or provenance.get("repo")
        or "biochem-pipeline-core"
    )
    source_commit = (
        manifest.get("source_commit")
        or provenance.get("source_commit")
        or provenance.get("git_commit")
        or "N/A"
    )
    intake_run_id = run_id or datetime.now(timezone.utc).strftime(
        f"%Y%m%d_%H%M_clinical_intake_{source_run_id}"
    )

    dest = suite_root / "clinical" / "intake_from_biochem" / intake_run_id
    dest.mkdir(parents=True, exist_ok=True)

    shutil.copy2(manifest_path, dest / "manifest.json")
    shutil.copy2(candidates_path, dest / "candidates.csv")
    shutil.copy2(provenance_path, dest / "provenance.json")

    receipt = {
        "receipt_version": "1.0",
        "imported_utc": _utc_now(),
        "source_package": str(src),
        "source_run_id": source_run_id,
        "intake_run_id": intake_run_id,
        "records": n_rows,
        "notes": notes,
    }
    (dest / "import_receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    db = RepurposingDB(db_path)
    db.init_schema()
    db.upsert_biochem_intake_run(
        {
            "intake_run_id": intake_run_id,
            "source_run_id": source_run_id,
            "source_repo": source_repo,
            "source_commit": source_commit,
            "source_package_path": str(src),
            "imported_package_path": str(dest),
            "records": n_rows,
            "notes": notes,
            "imported_utc": receipt["imported_utc"],
        }
    )
    db.upsert_biochem_intake_candidates(intake_run_id=intake_run_id, candidates=candidates)

    _append_index(
        suite_root=suite_root,
        run_id=intake_run_id,
        package_path=dest,
        source_repo=source_repo,
        source_commit=source_commit,
        records=n_rows,
        notes=notes or f"imported_from={src}",
    )
    return intake_run_id, dest, n_rows


def _list_intake_run(db_path: Path, intake_run_id: str, limit: int | None) -> int:
    db = RepurposingDB(db_path)
    db.init_schema()
    rows = db.list_biochem_intake_candidates(intake_run_id, limit=limit)
    if not rows:
        print(f"No candidates found for intake_run_id={intake_run_id}")
        return 0

    print("intake_run_id\tcompound_id\ttarget_id\trank_t1\trank_t2\tscore_t1\tscore_t2")
    for row in rows:
        print(
            f"{row['intake_run_id']}\t{row['compound_id']}\t{row['target_id']}\t"
            f"{row['rank_t1']}\t{row['rank_t2']}\t{row['score_t1']}\t{row['score_t2']}"
        )
    return len(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description="Import biochem package into clinical intake lane")
    ap.add_argument("--package", type=Path, help="Path to source biochem package directory")
    ap.add_argument("--suite-root", type=Path, default=DEFAULT_SUITE_ROOT)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to clinical SQLite DB")
    ap.add_argument("--run-id", type=str, default=None, help="Override intake run_id")
    ap.add_argument("--notes", type=str, default="")
    ap.add_argument("--list-intake-run", type=str, default=None, help="List candidates for an intake_run_id")
    ap.add_argument("--limit", type=int, default=None, help="Optional row limit for --list-intake-run")
    args = ap.parse_args()

    if args.list_intake_run:
        _list_intake_run(db_path=args.db, intake_run_id=args.list_intake_run, limit=args.limit)
        return

    if args.package is None:
        raise SystemExit("Either --package or --list-intake-run is required.")

    try:
        intake_run_id, dest, n_rows = import_package(
            package=args.package,
            suite_root=args.suite_root,
            db_path=args.db,
            run_id=args.run_id,
            notes=args.notes,
        )
    except ValueError as exc:
        raise SystemExit(str(exc))

    print(f"Imported {n_rows} rows to: {dest} (intake_run_id={intake_run_id}, db={args.db})")


if __name__ == "__main__":
    main()
