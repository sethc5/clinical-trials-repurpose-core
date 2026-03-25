from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml


def _run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def _write_runtime_config(path: Path, suite_root: Path, genomics_repo: Path, biochem_repo: Path, clinical_repo: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "paths": {
                    "suite_root": str(suite_root),
                    "genomics_repo": str(genomics_repo),
                    "biochem_repo": str(biochem_repo),
                    "clinical_repo": str(clinical_repo),
                },
                "commands": {
                    "genomics_export_handoff": "echo genomics_export",
                    "biochem_finalize_export": "echo biochem_finalize",
                    "clinical_import": "echo clinical_import intake_run_id=dryrun_intake_test",
                    "clinical_build": "echo clinical_build build_run_id=dryrun_build_test",
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_orchestrator_biochem_to_clinical_dry_run(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "suite_orchestrator.py"
    db = tmp_path / "orchestrator.db"
    runtime = tmp_path / "runtime.yaml"
    backlog = tmp_path / "backlog.yaml"

    suite_root = tmp_path / "suite_handoff"
    genomics_repo = tmp_path / "genomics_repo"
    biochem_repo = tmp_path / "biochem_repo"
    clinical_repo = tmp_path / "clinical_repo"
    for p in (suite_root, genomics_repo, biochem_repo, clinical_repo):
        p.mkdir(parents=True, exist_ok=True)

    (biochem_repo / "configs").mkdir(parents=True, exist_ok=True)
    (biochem_repo / "configs" / "ntd_tb_inha.yaml").write_text(
        yaml.safe_dump({"target": {"id": "InhA_mtb"}}),
        encoding="utf-8",
    )

    package_dir = suite_root / "biochem" / "t2_validated" / "20260325_2200_biochem_InhA_mtb_t2_validated"
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "manifest.json").write_text(
        yaml.safe_dump({"target_id": "InhA_mtb"}),
        encoding="utf-8",
    )

    _write_runtime_config(runtime, suite_root, genomics_repo, biochem_repo, clinical_repo)
    backlog.write_text(
        yaml.safe_dump(
            {
                "jobs": [
                    {
                        "job_id": "tb_inha_flow",
                        "job_type": "biochem_to_clinical",
                        "priority": 10,
                        "max_attempts": 2,
                        "biochem_config": "configs/ntd_tb_inha.yaml",
                        "handoff_state": "t2_validated",
                        "top": 50,
                        "clinical_db": "results/repurposing.db",
                        "clinical_profile_config": "configs/clinical_build_profiles.yaml",
                        "clinical_profile_provisional": "provisional_tb",
                        "clinical_profile_strict": "strict_tb",
                        "job_suffix": "tb_inha",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert _run(script, "--db", str(db), "init").returncode == 0
    enq = _run(script, "--db", str(db), "enqueue", "--backlog", str(backlog))
    assert enq.returncode == 0
    assert "enqueued: 1" in enq.stdout

    # Stage 0: biochem finalize
    assert _run(script, "--db", str(db), "--runtime-config", str(runtime), "run-once").returncode == 0
    # Stage 1: review checkpoint -> waiting_review
    assert _run(script, "--db", str(db), "--runtime-config", str(runtime), "run-once").returncode == 0
    st_wait = _run(script, "--db", str(db), "status")
    assert "waiting_review" in st_wait.stdout
    assert _run(script, "--db", str(db), "approve", "--job-id", "tb_inha_flow").returncode == 0

    # Stage 2 discover package, Stage 3 import, Stage 4 provisional build
    assert _run(script, "--db", str(db), "--runtime-config", str(runtime), "run-once").returncode == 0
    assert _run(script, "--db", str(db), "--runtime-config", str(runtime), "run-once").returncode == 0
    assert _run(script, "--db", str(db), "--runtime-config", str(runtime), "run-once").returncode == 0

    # Stage 5 review checkpoint -> waiting_review
    assert _run(script, "--db", str(db), "--runtime-config", str(runtime), "run-once").returncode == 0
    st_wait2 = _run(script, "--db", str(db), "status")
    assert "waiting_review" in st_wait2.stdout
    assert _run(script, "--db", str(db), "approve", "--job-id", "tb_inha_flow").returncode == 0

    # Stage 6 strict build -> completed
    final_step = _run(script, "--db", str(db), "--runtime-config", str(runtime), "run-once")
    assert final_step.returncode == 0
    st_done = _run(script, "--db", str(db), "status")
    assert "completed" in st_done.stdout


def test_orchestrator_enqueue_is_idempotent(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "suite_orchestrator.py"
    db = tmp_path / "orchestrator.db"
    backlog = tmp_path / "backlog.yaml"
    backlog.write_text(
        yaml.safe_dump(
            {
                "jobs": [
                    {"job_id": "job_a", "job_type": "genomics_to_biochem"},
                    {"job_id": "job_b", "job_type": "biochem_to_clinical", "biochem_config": "configs/x.yaml"},
                ]
            }
        ),
        encoding="utf-8",
    )

    assert _run(script, "--db", str(db), "init").returncode == 0
    first = _run(script, "--db", str(db), "enqueue", "--backlog", str(backlog))
    assert first.returncode == 0
    assert "enqueued: 2" in first.stdout

    second = _run(script, "--db", str(db), "enqueue", "--backlog", str(backlog))
    assert second.returncode == 0
    assert "enqueued: 0" in second.stdout


def test_orchestrator_compute_profile_overrides_command(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "suite_orchestrator.py"
    db = tmp_path / "orchestrator.db"
    runtime = tmp_path / "runtime.yaml"
    backlog = tmp_path / "backlog.yaml"

    suite_root = tmp_path / "suite_handoff"
    genomics_repo = tmp_path / "genomics_repo"
    biochem_repo = tmp_path / "biochem_repo"
    clinical_repo = tmp_path / "clinical_repo"
    for p in (suite_root, genomics_repo, biochem_repo, clinical_repo):
        p.mkdir(parents=True, exist_ok=True)

    runtime.write_text(
        yaml.safe_dump(
            {
                "paths": {
                    "suite_root": str(suite_root),
                    "genomics_repo": str(genomics_repo),
                    "biochem_repo": str(biochem_repo),
                    "clinical_repo": str(clinical_repo),
                },
                "commands": {
                    "genomics_export_handoff": "echo default_export",
                },
                "profiles": {
                    "runpod_flash": {
                        "commands": {
                            "genomics_export_handoff": "echo runpod_flash_export",
                        }
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    backlog.write_text(
        yaml.safe_dump(
            {
                "jobs": [
                    {
                        "job_id": "g_job",
                        "job_type": "genomics_to_biochem",
                        "genomics_db": "results/genomics.db",
                        "genomics_target_id": "target_x",
                        "top": 20,
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert _run(script, "--db", str(db), "init").returncode == 0
    assert _run(script, "--db", str(db), "enqueue", "--backlog", str(backlog)).returncode == 0
    run_one = _run(
        script,
        "--db",
        str(db),
        "--runtime-config",
        str(runtime),
        "--compute-profile",
        "runpod_flash",
        "run-once",
    )
    assert run_one.returncode == 0
    events = _run(script, "--db", str(db), "events", "--job-id", "g_job")
    assert events.returncode == 0
    assert "runpod_flash_export" in events.stdout
