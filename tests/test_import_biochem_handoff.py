from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path


def _write_package(package_dir: Path, candidates_csv: str) -> None:
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "manifest.json").write_text(
        json.dumps(
            {
                "artifact_type": "candidate_package",
                "run_id": "tb_inha_top25_t2",
                "source_repo": "biochem-pipeline-core",
                "source_commit": "deadbeef",
            }
        ),
        encoding="utf-8",
    )
    (package_dir / "provenance.json").write_text(
        json.dumps(
            {
                "source_repo": "biochem-pipeline-core",
                "source_commit": "deadbeef",
            }
        ),
        encoding="utf-8",
    )
    (package_dir / "candidates.csv").write_text(candidates_csv, encoding="utf-8")


def _run_import(script_path: Path, package_dir: Path, suite_root: Path, db_path: Path, run_id: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--package",
            str(package_dir),
            "--suite-root",
            str(suite_root),
            "--db",
            str(db_path),
            "--run-id",
            run_id,
        ],
        check=False,
        text=True,
        capture_output=True,
    )


def test_required_column_validation(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "import_biochem_handoff.py"
    package_dir = tmp_path / "bad_pkg"
    suite_root = tmp_path / "suite_handoff"
    db_path = tmp_path / "clinical.db"
    run_id = "20260325_1409_clinical_intake_missing_target"

    _write_package(
        package_dir,
        "compound_id,smiles\ncmp1,CCO\n",
    )

    proc = _run_import(script_path, package_dir, suite_root, db_path, run_id)
    assert proc.returncode != 0
    err = f"{proc.stderr}\n{proc.stdout}"
    assert "missing required columns" in err
    assert "target_id" in err


def test_import_idempotency(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "import_biochem_handoff.py"
    package_dir = tmp_path / "good_pkg"
    suite_root = tmp_path / "suite_handoff"
    db_path = tmp_path / "clinical.db"
    run_id = "20260325_1409_clinical_intake_tb_inha_top25_t2"

    _write_package(
        package_dir,
        (
            "compound_id,smiles,target_id,score_t1,score_t2,rank_t1,rank_t2\n"
            "cmp1,CCO,InhA,0.9,0.8,1,2\n"
            "cmp2,CCC,KasA,0.8,0.7,2,5\n"
        ),
    )

    first = _run_import(script_path, package_dir, suite_root, db_path, run_id)
    assert first.returncode == 0, first.stderr

    second = _run_import(script_path, package_dir, suite_root, db_path, run_id)
    assert second.returncode == 0, second.stderr

    conn = sqlite3.connect(db_path)
    try:
        run_rows = conn.execute(
            "SELECT COUNT(*) FROM biochem_intake_runs WHERE intake_run_id=?",
            (run_id,),
        ).fetchone()[0]
        candidate_rows = conn.execute(
            "SELECT COUNT(*) FROM biochem_intake_candidates WHERE intake_run_id=?",
            (run_id,),
        ).fetchone()[0]
    finally:
        conn.close()

    assert run_rows == 1
    assert candidate_rows == 2

    index_path = suite_root / "INDEX.md"
    content = index_path.read_text(encoding="utf-8")
    marker = f"| clinical | intake_from_biochem | {run_id} |"
    assert content.count(marker) == 1


def test_import_backfills_rank_t1_when_missing(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "import_biochem_handoff.py"
    package_dir = tmp_path / "legacy_pkg"
    suite_root = tmp_path / "suite_handoff"
    db_path = tmp_path / "clinical.db"
    run_id = "20260327_1500_clinical_intake_legacy_rank"

    _write_package(
        package_dir,
        (
            "compound_id,smiles,target_id,t1_score,t2_rmsd,t2_persistence\n"
            "cmp2,CCC,InhA,-10.10,2.8,0.7\n"
            "cmp1,CCO,InhA,-10.90,2.2,0.8\n"
        ),
    )

    proc = _run_import(script_path, package_dir, suite_root, db_path, run_id)
    assert proc.returncode == 0, proc.stderr

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT compound_id, rank_t1
            FROM biochem_intake_candidates
            WHERE intake_run_id=?
            ORDER BY compound_id
            """,
            (run_id,),
        ).fetchall()
    finally:
        conn.close()

    assert rows == [("cmp1", 1), ("cmp2", 2)]
