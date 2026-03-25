#!/usr/bin/env python3
"""
Supervised suite orchestrator for genomics -> biochem -> clinical handoff loops.

This MVP is intentionally human-in-the-loop:
- persistent queue in SQLite
- one-stage-at-a-time execution
- review checkpoints between high-risk transitions
- dry-run by default unless --execute is set
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "results" / "orchestrator.db"
DEFAULT_RUNTIME_CONFIG = REPO_ROOT / "configs" / "suite_orchestrator.yaml"


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id               TEXT PRIMARY KEY,
    job_type             TEXT NOT NULL,
    priority             INTEGER NOT NULL DEFAULT 100,
    status               TEXT NOT NULL,
    current_stage_index  INTEGER NOT NULL DEFAULT 0,
    spec_json            TEXT NOT NULL,
    context_json         TEXT NOT NULL,
    checkpoint_stage     TEXT,
    attempts             INTEGER NOT NULL DEFAULT 0,
    max_attempts         INTEGER NOT NULL DEFAULT 3,
    last_error           TEXT,
    created_utc          TEXT NOT NULL,
    updated_utc          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_events (
    event_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id               TEXT NOT NULL,
    event_utc            TEXT NOT NULL,
    event_type           TEXT NOT NULL,
    stage_id             TEXT,
    message              TEXT,
    payload_json         TEXT
);
"""


VALID_JOB_TYPES = {"genomics_to_biochem", "biochem_to_clinical"}
ACTIVE_STATUSES = {"queued", "running", "waiting_review", "failed", "completed"}


@dataclass
class Stage:
    stage_id: str
    requires_review: bool


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _j(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True)


def _pj(s: str | None, default: Any) -> Any:
    if not s:
        return default
    return json.loads(s)


def _conn(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Path) -> None:
    with _conn(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()


def _event(conn: sqlite3.Connection, job_id: str, event_type: str, stage_id: str | None, message: str, payload: dict | None = None) -> None:
    conn.execute(
        """
        INSERT INTO job_events (job_id, event_utc, event_type, stage_id, message, payload_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (job_id, _utc_now(), event_type, stage_id, message, _j(payload or {})),
    )


def load_runtime_config(path: Path) -> dict:
    if not path.exists():
        raise ValueError(f"runtime config not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"runtime config must be mapping: {path}")
    return raw


def resolve_runtime_config(raw: dict, compute_profile: str | None) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("runtime config must be mapping")

    resolved = dict(raw)
    resolved["paths"] = dict(raw.get("paths") or {})
    resolved["commands"] = dict(raw.get("commands") or {})

    if not compute_profile:
        return resolved

    profiles = raw.get("profiles") or {}
    if not isinstance(profiles, dict):
        raise ValueError("runtime config profiles must be mapping")
    profile = profiles.get(compute_profile)
    if not isinstance(profile, dict):
        raise ValueError(f"runtime profile not found: {compute_profile}")

    for section in ("paths", "commands"):
        overrides = profile.get(section) or {}
        if not isinstance(overrides, dict):
            raise ValueError(f"profile {compute_profile} section {section} must be mapping")
        resolved[section].update(overrides)
    return resolved


def load_backlog(path: Path) -> list[dict]:
    if not path.exists():
        raise ValueError(f"backlog file not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    jobs = raw.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError(f"backlog {path} must define jobs list")
    return jobs


def enqueue_jobs(db_path: Path, backlog_path: Path) -> int:
    init_db(db_path)
    jobs = load_backlog(backlog_path)
    inserted = 0
    now = _utc_now()
    with _conn(db_path) as conn:
        for item in jobs:
            job_id = str(item.get("job_id") or "").strip()
            job_type = str(item.get("job_type") or "").strip()
            if not job_id:
                raise ValueError("each backlog job requires job_id")
            if job_type not in VALID_JOB_TYPES:
                raise ValueError(f"job {job_id}: job_type must be one of {sorted(VALID_JOB_TYPES)}")

            exists = conn.execute("SELECT 1 FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if exists:
                continue
            priority = int(item.get("priority", 100))
            max_attempts = int(item.get("max_attempts", 3))
            spec = dict(item)
            spec.pop("job_id", None)
            spec.pop("job_type", None)
            conn.execute(
                """
                INSERT INTO jobs (
                    job_id, job_type, priority, status, current_stage_index, spec_json, context_json,
                    checkpoint_stage, attempts, max_attempts, last_error, created_utc, updated_utc
                ) VALUES (?, ?, ?, 'queued', 0, ?, '{}', NULL, 0, ?, NULL, ?, ?)
                """,
                (job_id, job_type, priority, _j(spec), max_attempts, now, now),
            )
            _event(conn, job_id, "enqueue", None, "queued from backlog", {"backlog_file": str(backlog_path)})
            inserted += 1
        conn.commit()
    return inserted


def _resolve_stage_plan(job_type: str) -> list[Stage]:
    if job_type == "genomics_to_biochem":
        return [
            Stage("genomics_export_handoff", False),
            Stage("review_genomics_export", True),
        ]
    if job_type == "biochem_to_clinical":
        return [
            Stage("biochem_finalize_export", False),
            Stage("review_biochem_export", True),
            Stage("discover_biochem_package", False),
            Stage("clinical_import", False),
            Stage("clinical_build_provisional", False),
            Stage("review_before_strict", True),
            Stage("clinical_build_strict", False),
        ]
    raise ValueError(f"unknown job_type={job_type}")


def _fmt(template: str, values: dict[str, Any]) -> str:
    out = template
    for key, value in values.items():
        out = out.replace("{" + key + "}", str(value))
    return out


def _run_shell(cmd: str, cwd: Path, execute: bool) -> tuple[int, str]:
    if not execute:
        return 0, f"[dry-run] {cmd}"
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        shell=True,
        text=True,
        capture_output=True,
    )
    text = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return proc.returncode, text.strip()


def _load_yaml_target_id(config_path: Path) -> str:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    target = raw.get("target") or {}
    target_id = target.get("id")
    if not target_id:
        raise ValueError(f"target.id missing in config: {config_path}")
    return str(target_id)


def _stage_genomics_export_handoff(
    spec: dict,
    context: dict,
    runtime: dict,
    execute: bool,
) -> tuple[bool, str, dict]:
    template = (
        runtime.get("commands", {}).get("genomics_export_handoff")
        or "cd {genomics_repo} && python3 scripts/export_handoff_targets.py --db {genomics_db} --target-id {genomics_target_id} --state handoff_to_biochem --top {top} --suite-root {suite_root}"
    )
    values = {
        "genomics_repo": runtime["paths"]["genomics_repo"],
        "genomics_db": spec["genomics_db"],
        "genomics_target_id": spec["genomics_target_id"],
        "suite_root": runtime["paths"]["suite_root"],
        "top": spec.get("top", 200),
    }
    cmd = _fmt(template, values)
    rc, text = _run_shell(cmd, cwd=Path(runtime["paths"]["genomics_repo"]), execute=execute)
    return (rc == 0), text, context


def _stage_biochem_finalize_export(
    spec: dict,
    context: dict,
    runtime: dict,
    execute: bool,
) -> tuple[bool, str, dict]:
    template = (
        runtime.get("commands", {}).get("biochem_finalize_export")
        or "cd {biochem_repo} && python3 scripts/finalize_t2_pipeline.py --config {biochem_config} --top {top} --handoff-state {handoff_state} --suite-root {suite_root}"
    )
    values = {
        "biochem_repo": runtime["paths"]["biochem_repo"],
        "biochem_config": spec["biochem_config"],
        "top": spec.get("top", 50),
        "handoff_state": spec.get("handoff_state", "t2_validated"),
        "suite_root": runtime["paths"]["suite_root"],
    }
    cmd = _fmt(template, values)
    rc, text = _run_shell(cmd, cwd=Path(runtime["paths"]["biochem_repo"]), execute=execute)
    return (rc == 0), text, context


def _stage_discover_biochem_package(
    spec: dict,
    context: dict,
    runtime: dict,
    execute: bool,
) -> tuple[bool, str, dict]:
    del execute
    biochem_config = Path(runtime["paths"]["biochem_repo"]) / spec["biochem_config"]
    target_id = _load_yaml_target_id(biochem_config)
    state = spec.get("handoff_state", "t2_validated")
    root = Path(runtime["paths"]["suite_root"]) / "biochem" / state
    if not root.exists():
        return False, f"state directory not found: {root}", context

    candidates = sorted(
        [p for p in root.iterdir() if p.is_dir() and (p / "manifest.json").exists()],
        key=lambda p: p.name,
        reverse=True,
    )
    chosen: Path | None = None
    for package in candidates:
        manifest = yaml.safe_load((package / "manifest.json").read_text(encoding="utf-8")) or {}
        if str(manifest.get("target_id") or "") == target_id:
            chosen = package
            break
    if chosen is None:
        return False, f"no package found under {root} for target_id={target_id}", context

    context = dict(context)
    context["biochem_package_path"] = str(chosen)
    context["biochem_target_id"] = target_id
    return True, f"selected package: {chosen}", context


def _stage_clinical_import(
    spec: dict,
    context: dict,
    runtime: dict,
    execute: bool,
) -> tuple[bool, str, dict]:
    package = context.get("biochem_package_path")
    if not package:
        return False, "biochem_package_path missing from context", context

    template = (
        runtime.get("commands", {}).get("clinical_import")
        or "cd {clinical_repo} && python3 scripts/import_biochem_handoff.py --package {package} --suite-root {suite_root} --db {clinical_db}"
    )
    values = {
        "clinical_repo": runtime["paths"]["clinical_repo"],
        "package": package,
        "suite_root": runtime["paths"]["suite_root"],
        "clinical_db": spec.get("clinical_db", "results/repurposing.db"),
    }
    cmd = _fmt(template, values)
    rc, text = _run_shell(cmd, cwd=Path(runtime["paths"]["clinical_repo"]), execute=execute)
    if rc != 0:
        return False, text, context

    ctx = dict(context)
    if not execute:
        ctx["clinical_intake_run_id"] = f"dryrun_intake_{spec.get('job_suffix', 'job')}"
        return True, text, ctx

    match = re.search(r"intake_run_id=([A-Za-z0-9_\\-\\.]+)", text)
    if match:
        ctx["clinical_intake_run_id"] = match.group(1)
    return True, text, ctx


def _stage_clinical_build(
    stage_name: str,
    profile: str,
    spec: dict,
    context: dict,
    runtime: dict,
    execute: bool,
) -> tuple[bool, str, dict]:
    intake = context.get("clinical_intake_run_id")
    if not intake:
        return False, "clinical_intake_run_id missing from context", context

    template = (
        runtime.get("commands", {}).get("clinical_build")
        or "cd {clinical_repo} && python3 scripts/clinical_build.py --db {clinical_db} --intake-run-id {intake_run_id} --profile-config {profile_config} --profile {profile}"
    )
    values = {
        "clinical_repo": runtime["paths"]["clinical_repo"],
        "clinical_db": spec.get("clinical_db", "results/repurposing.db"),
        "intake_run_id": intake,
        "profile_config": spec.get("clinical_profile_config", "configs/clinical_build_profiles.yaml"),
        "profile": profile,
    }
    cmd = _fmt(template, values)
    rc, text = _run_shell(cmd, cwd=Path(runtime["paths"]["clinical_repo"]), execute=execute)
    if rc != 0:
        return False, text, context
    ctx = dict(context)
    if not execute:
        ctx[f"clinical_build_{profile}_id"] = f"dryrun_build_{profile}_{spec.get('job_suffix', 'job')}"
        return True, text, ctx

    match = re.search(r"build_run_id=([A-Za-z0-9_\\-\\.]+)", text)
    if match:
        ctx[f"clinical_build_{profile}_id"] = match.group(1)
    return True, text, ctx


def _execute_stage(
    stage_id: str,
    spec: dict,
    context: dict,
    runtime: dict,
    execute: bool,
) -> tuple[bool, str, dict]:
    if stage_id == "genomics_export_handoff":
        return _stage_genomics_export_handoff(spec, context, runtime, execute)
    if stage_id == "biochem_finalize_export":
        return _stage_biochem_finalize_export(spec, context, runtime, execute)
    if stage_id == "discover_biochem_package":
        return _stage_discover_biochem_package(spec, context, runtime, execute)
    if stage_id == "clinical_import":
        return _stage_clinical_import(spec, context, runtime, execute)
    if stage_id == "clinical_build_provisional":
        return _stage_clinical_build(
            stage_name=stage_id,
            profile=spec.get("clinical_profile_provisional", "provisional_tb"),
            spec=spec,
            context=context,
            runtime=runtime,
            execute=execute,
        )
    if stage_id == "clinical_build_strict":
        return _stage_clinical_build(
            stage_name=stage_id,
            profile=spec.get("clinical_profile_strict", "strict_tb"),
            spec=spec,
            context=context,
            runtime=runtime,
            execute=execute,
        )
    if stage_id.startswith("review_"):
        return True, "review checkpoint passed", context
    return False, f"unknown stage_id={stage_id}", context


def _choose_next_job(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM jobs
        WHERE status IN ('queued', 'running')
        ORDER BY priority ASC, created_utc ASC
        LIMIT 1
        """
    ).fetchone()


def run_once(db_path: Path, runtime_config: Path, execute: bool, compute_profile: str | None = None) -> str:
    init_db(db_path)
    runtime_raw = load_runtime_config(runtime_config)
    runtime = resolve_runtime_config(runtime_raw, compute_profile)
    with _conn(db_path) as conn:
        row = _choose_next_job(conn)
        if row is None:
            return "no queued/running jobs"

        job_id = row["job_id"]
        job_type = row["job_type"]
        spec = _pj(row["spec_json"], {})
        context = _pj(row["context_json"], {})
        stage_plan = _resolve_stage_plan(job_type)
        stage_idx = int(row["current_stage_index"])

        if stage_idx >= len(stage_plan):
            conn.execute(
                "UPDATE jobs SET status='completed', updated_utc=? WHERE job_id=?",
                (_utc_now(), job_id),
            )
            _event(conn, job_id, "complete", None, "all stages finished")
            conn.commit()
            return f"{job_id}: completed"

        stage = stage_plan[stage_idx]
        conn.execute(
            "UPDATE jobs SET status='running', updated_utc=? WHERE job_id=?",
            (_utc_now(), job_id),
        )
        _event(conn, job_id, "stage_start", stage.stage_id, f"running stage {stage.stage_id}", {"execute": execute})

        ok, output, new_context = _execute_stage(
            stage_id=stage.stage_id,
            spec=spec,
            context=context,
            runtime=runtime,
            execute=execute,
        )

        if ok:
            new_stage_idx = stage_idx + 1
            if stage.requires_review:
                new_status = "waiting_review"
                checkpoint = stage.stage_id
            elif new_stage_idx >= len(stage_plan):
                new_status = "completed"
                checkpoint = None
            else:
                new_status = "queued"
                checkpoint = None

            conn.execute(
                """
                UPDATE jobs
                SET status=?, current_stage_index=?, context_json=?, checkpoint_stage=?, updated_utc=?, last_error=NULL
                WHERE job_id=?
                """,
                (new_status, new_stage_idx, _j(new_context), checkpoint, _utc_now(), job_id),
            )
            _event(conn, job_id, "stage_ok", stage.stage_id, output, {"next_status": new_status})
            conn.commit()
            return f"{job_id}: {stage.stage_id} ok -> {new_status}"

        attempts = int(row["attempts"]) + 1
        max_attempts = int(row["max_attempts"])
        failed_hard = attempts >= max_attempts
        new_status = "failed" if failed_hard else "queued"
        conn.execute(
            """
            UPDATE jobs
            SET status=?, attempts=?, last_error=?, updated_utc=?
            WHERE job_id=?
            """,
            (new_status, attempts, output[:8000], _utc_now(), job_id),
        )
        _event(conn, job_id, "stage_fail", stage.stage_id, output, {"attempt": attempts, "max_attempts": max_attempts})
        conn.commit()
        return f"{job_id}: {stage.stage_id} failed ({attempts}/{max_attempts}) -> {new_status}"


def approve_job(db_path: Path, job_id: str) -> str:
    init_db(db_path)
    with _conn(db_path) as conn:
        row = conn.execute("SELECT status, checkpoint_stage FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            return f"{job_id}: not found"
        if row["status"] != "waiting_review":
            return f"{job_id}: status={row['status']} (no approval needed)"
        conn.execute(
            """
            UPDATE jobs
            SET status='queued', checkpoint_stage=NULL, updated_utc=?
            WHERE job_id=?
            """,
            (_utc_now(), job_id),
        )
        _event(conn, job_id, "approved", row["checkpoint_stage"], "checkpoint approved")
        conn.commit()
    return f"{job_id}: approved"


def status_table(db_path: Path, limit: int) -> str:
    init_db(db_path)
    with _conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT job_id, job_type, status, priority, current_stage_index, checkpoint_stage, attempts, max_attempts, updated_utc
            FROM jobs
            ORDER BY
              CASE status
                WHEN 'running' THEN 0
                WHEN 'queued' THEN 1
                WHEN 'waiting_review' THEN 2
                WHEN 'failed' THEN 3
                WHEN 'completed' THEN 4
                ELSE 9
              END,
              priority ASC,
              updated_utc DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    if not rows:
        return "no jobs"
    lines = ["job_id\tjob_type\tstatus\tpriority\tstage_idx\tcheckpoint\tattempts\tupdated_utc"]
    for r in rows:
        lines.append(
            f"{r['job_id']}\t{r['job_type']}\t{r['status']}\t{r['priority']}\t"
            f"{r['current_stage_index']}\t{r['checkpoint_stage'] or ''}\t"
            f"{r['attempts']}/{r['max_attempts']}\t{r['updated_utc']}"
        )
    return "\n".join(lines)


def show_events(db_path: Path, job_id: str, limit: int) -> str:
    init_db(db_path)
    with _conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT event_utc, event_type, stage_id, message
            FROM job_events
            WHERE job_id=?
            ORDER BY event_id DESC
            LIMIT ?
            """,
            (job_id, limit),
        ).fetchall()
    if not rows:
        return f"{job_id}: no events"
    lines = ["event_utc\tevent_type\tstage_id\tmessage"]
    for r in rows:
        msg = str(r["message"] or "").replace("\n", " ")[:220]
        lines.append(f"{r['event_utc']}\t{r['event_type']}\t{r['stage_id'] or ''}\t{msg}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Supervised suite orchestrator (genomics -> biochem -> clinical)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--runtime-config", type=Path, default=DEFAULT_RUNTIME_CONFIG)
    parser.add_argument("--compute-profile", default=None, help="Optional runtime profile override (e.g. hetzner, runpod_flash)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Initialize orchestrator DB")

    p_enqueue = sub.add_parser("enqueue", help="Enqueue jobs from backlog YAML")
    p_enqueue.add_argument("--backlog", required=True, type=Path)

    p_run = sub.add_parser("run-once", help="Execute one stage of one job")
    p_run.add_argument("--execute", action="store_true", help="Actually execute commands (default is dry-run)")

    p_approve = sub.add_parser("approve", help="Approve waiting_review checkpoint for a job")
    p_approve.add_argument("--job-id", required=True)

    p_status = sub.add_parser("status", help="Show queue status")
    p_status.add_argument("--limit", type=int, default=50)

    p_events = sub.add_parser("events", help="Show event history for one job")
    p_events.add_argument("--job-id", required=True)
    p_events.add_argument("--limit", type=int, default=40)

    args = parser.parse_args()

    if args.cmd == "init":
        init_db(args.db)
        print(f"initialized: {args.db}")
        return
    if args.cmd == "enqueue":
        n = enqueue_jobs(args.db, args.backlog)
        print(f"enqueued: {n}")
        return
    if args.cmd == "run-once":
        print(run_once(args.db, args.runtime_config, execute=bool(args.execute), compute_profile=args.compute_profile))
        return
    if args.cmd == "approve":
        print(approve_job(args.db, args.job_id))
        return
    if args.cmd == "status":
        print(status_table(args.db, args.limit))
        return
    if args.cmd == "events":
        print(show_events(args.db, args.job_id, args.limit))
        return


if __name__ == "__main__":
    main()
