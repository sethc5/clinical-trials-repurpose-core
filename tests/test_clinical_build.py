from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

from db_utils import RepurposingDB


def _seed_intake(db: RepurposingDB, intake_run_id: str, candidates: list[dict]) -> None:
    db.upsert_biochem_intake_run(
        {
            "intake_run_id": intake_run_id,
            "source_run_id": "tb_source_run",
            "source_repo": "biochem-pipeline-core",
            "source_commit": "abc123",
            "source_package_path": "/tmp/pkg",
            "imported_package_path": f"/tmp/suite/{intake_run_id}",
            "records": len(candidates),
            "notes": "seeded for tests",
            "imported_utc": "2026-03-25T20:00:00+00:00",
        }
    )
    db.upsert_biochem_intake_candidates(intake_run_id=intake_run_id, candidates=candidates)


def _write_profile_yaml(path: Path) -> None:
    path.write_text(
        """
version: "1.0"
profiles:
  provisional_tb:
    gates:
      require_t2_metrics: false
      max_t1_score: -9.50
      max_t2_rmsd: 5.60
      min_t2_persistence: 0.08
    scoring:
      weights:
        t1_score: 0.50
        t2_persistence: 0.30
        t2_rmsd: 0.20
      ranges:
        t1_score_min: -12.5
        t1_score_max: -8.0
        t2_persistence_min: 0.0
        t2_persistence_max: 1.0
        t2_rmsd_min: 2.0
        t2_rmsd_max: 12.0
      defaults:
        t1_score: -8.0
        t2_persistence: 0.0
        t2_rmsd: 12.0
    selection:
      top_k: 1
      include_gate_failures: false
  strict_tb:
    gates:
      require_t2_metrics: true
      max_t1_score: -9.50
      max_t2_rmsd: 5.60
      min_t2_persistence: 0.08
    scoring:
      weights:
        t1_score: 1.0
      ranges:
        t1_score_min: -12.5
        t1_score_max: -8.0
      defaults:
        t1_score: -8.0
    selection:
      top_k: 5
      include_gate_failures: false
""".strip()
        + "\n",
        encoding="utf-8",
    )


def _run_script(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    script = repo_root / "scripts" / "clinical_build.py"
    return subprocess.run(
        [sys.executable, str(script), *args],
        check=False,
        text=True,
        capture_output=True,
    )


def test_clinical_build_profile_and_idempotency(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    db_path = tmp_path / "clinical.db"
    profile_path = tmp_path / "profiles.yaml"
    csv_path = tmp_path / "build.csv"
    intake_run_id = "20260325_2000_clinical_intake_tb"
    build_run_id = "20260325_2010_provisional_tb_tb"

    _write_profile_yaml(profile_path)
    db = RepurposingDB(db_path)
    db.init_schema()
    _seed_intake(
        db,
        intake_run_id,
        [
            {
                "compound_id": "cmp_a",
                "smiles": "CCO",
                "target_id": "InhA_mtb",
                "source_row_json": {"t1_score": "-11.20", "t2_rmsd": "5.20", "t2_persistence": "0.12"},
            },
            {
                "compound_id": "cmp_b",
                "smiles": "CCC",
                "target_id": "InhA_mtb",
                "source_row_json": {"t1_score": "-10.60", "t2_rmsd": "5.40", "t2_persistence": "0.09"},
            },
            {
                "compound_id": "cmp_c",
                "smiles": "CCN",
                "target_id": "InhA_mtb",
                "source_row_json": {"t1_score": "-9.10", "t2_rmsd": "6.20", "t2_persistence": "0.02"},
            },
        ],
    )

    first = _run_script(
        repo_root,
        "--db",
        str(db_path),
        "--profile-config",
        str(profile_path),
        "--profile",
        "provisional_tb",
        "--intake-run-id",
        intake_run_id,
        "--build-run-id",
        build_run_id,
        "--out-csv",
        str(csv_path),
    )
    assert first.returncode == 0, first.stderr
    assert csv_path.exists()

    second = _run_script(
        repo_root,
        "--db",
        str(db_path),
        "--profile-config",
        str(profile_path),
        "--profile",
        "provisional_tb",
        "--intake-run-id",
        intake_run_id,
        "--build-run-id",
        build_run_id,
        "--out-csv",
        str(csv_path),
    )
    assert second.returncode == 0, second.stderr

    conn = sqlite3.connect(db_path)
    try:
        runs = conn.execute("SELECT COUNT(*) FROM clinical_build_runs WHERE build_run_id=?", (build_run_id,)).fetchone()[0]
        rows = conn.execute("SELECT COUNT(*) FROM clinical_build_candidates WHERE build_run_id=?", (build_run_id,)).fetchone()[0]
        included = conn.execute(
            "SELECT COUNT(*) FROM clinical_build_candidates WHERE build_run_id=? AND included=1",
            (build_run_id,),
        ).fetchone()[0]
        cmp_a_reason = conn.execute(
            "SELECT include_reason FROM clinical_build_candidates WHERE build_run_id=? AND compound_id='cmp_a'",
            (build_run_id,),
        ).fetchone()[0]
        cmp_b_reason = conn.execute(
            "SELECT include_reason FROM clinical_build_candidates WHERE build_run_id=? AND compound_id='cmp_b'",
            (build_run_id,),
        ).fetchone()[0]
    finally:
        conn.close()

    assert runs == 1
    assert rows == 3
    assert included == 1
    assert cmp_a_reason == "selected"
    assert cmp_b_reason == "below_top_k"


def test_clinical_build_strict_requires_t2_metrics(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    db_path = tmp_path / "clinical.db"
    profile_path = tmp_path / "profiles.yaml"
    intake_run_id = "20260325_2030_clinical_intake_tb"
    build_run_id = "20260325_2040_strict_tb_tb"

    _write_profile_yaml(profile_path)
    db = RepurposingDB(db_path)
    db.init_schema()
    _seed_intake(
        db,
        intake_run_id,
        [
            {
                "compound_id": "cmp_ok",
                "smiles": "CCO",
                "target_id": "KasA_mtb",
                "source_row_json": {"t1_score": "-10.80", "t2_rmsd": "5.20", "t2_persistence": "0.10"},
            },
            {
                "compound_id": "cmp_missing_t2",
                "smiles": "CCC",
                "target_id": "KasA_mtb",
                "source_row_json": {"t1_score": "-11.10"},
            },
        ],
    )

    run = _run_script(
        repo_root,
        "--db",
        str(db_path),
        "--profile-config",
        str(profile_path),
        "--profile",
        "strict_tb",
        "--intake-run-id",
        intake_run_id,
        "--build-run-id",
        build_run_id,
    )
    assert run.returncode == 0, run.stderr

    conn = sqlite3.connect(db_path)
    try:
        included = conn.execute(
            "SELECT COUNT(*) FROM clinical_build_candidates WHERE build_run_id=? AND included=1",
            (build_run_id,),
        ).fetchone()[0]
        reason = conn.execute(
            "SELECT include_reason FROM clinical_build_candidates WHERE build_run_id=? AND compound_id='cmp_missing_t2'",
            (build_run_id,),
        ).fetchone()[0]
    finally:
        conn.close()

    assert included == 1
    assert "missing_t2_metrics" in reason
