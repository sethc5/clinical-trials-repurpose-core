"""
db_utils.py — SQLite layer for the repurposing pipeline.

Provides RepurposingDB — single class encapsulating all reads/writes.
Schema mirrors the spec in the README exactly.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS drugs (
    drug_id             TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    generic_name        TEXT,
    brand_names         TEXT,
    drug_type           TEXT,
    status              TEXT,
    approval_date       TEXT,
    approved_indications TEXT,
    mechanism_of_action TEXT,
    pharmacodynamics    TEXT,
    half_life           TEXT,
    bioavailability     REAL,
    protein_binding     REAL,
    molecular_formula   TEXT,
    mw                  REAL,
    logp                REAL,
    smiles              TEXT,
    inchi_key           TEXT,
    black_box_warnings  TEXT,
    contraindications   TEXT,
    serious_aes         TEXT,
    pregnancy_category  TEXT,
    controlled_substance TEXT,
    primary_targets     TEXT,
    all_targets         TEXT,
    pathway_ids         TEXT,
    source              TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS indications (
    indication_id       TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    mesh_id             TEXT,
    omim_id             TEXT,
    orphanet_id         TEXT,
    icd10_code          TEXT,
    disease_genes       TEXT,
    pathway_ids         TEXT,
    go_terms            TEXT,
    transcriptomic_sig  TEXT,
    prevalence          REAL,
    unmet_need_score    REAL,
    orphan_status       BOOLEAN,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trials (
    trial_id            TEXT PRIMARY KEY,
    title               TEXT,
    status              TEXT,
    phase               TEXT,
    drug_id             TEXT REFERENCES drugs,
    indication_id       TEXT REFERENCES indications,
    start_date          TEXT,
    completion_date     TEXT,
    enrollment          INTEGER,
    primary_outcome     TEXT,
    result_summary      TEXT,
    success             BOOLEAN,
    termination_reason  TEXT,
    sponsor             TEXT,
    source              TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS targets (
    target_id           TEXT PRIMARY KEY,
    name                TEXT,
    description         TEXT,
    disease_context     TEXT,
    pathway_ids         TEXT,
    gene_set            TEXT,
    unmet_need          TEXT,
    safety_exclusions   TEXT,
    population_context  TEXT,
    evidence_threshold  REAL,
    priority_mechanisms TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    run_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    drug_id             TEXT REFERENCES drugs,
    indication_id       TEXT REFERENCES indications,
    target_id           TEXT REFERENCES targets,

    t0_pass             BOOLEAN,
    t0_mechanism_overlap REAL,
    t0_safety_compatible BOOLEAN,
    t0_already_tried    BOOLEAN,
    t0_reject_reason    TEXT,

    t025_pass           BOOLEAN,
    t025_network_proximity REAL,
    t025_transcriptomic_score REAL,
    t025_literature_cooccurrence INTEGER,
    t025_failed_trial   BOOLEAN,
    t025_failed_trial_id TEXT,

    t1_pass             BOOLEAN,
    t1_pathway_overlap  TEXT,
    t1_polypharmacology TEXT,
    t1_ae_profile       TEXT,
    t1_evidence_papers  TEXT,
    t1_evidence_score   REAL,
    t1_mechanistic_score REAL,
    t1_safety_score     REAL,

    t2_pass             BOOLEAN,
    t2_evidence_summary TEXT,
    t2_biomarkers       TEXT,
    t2_dose_rationale   TEXT,
    t2_trial_design     TEXT,
    t2_endpoints        TEXT,
    t2_population       TEXT,
    t2_competitive_landscape TEXT,
    t2_confidence       REAL,
    t2_novelty          REAL,

    fto_risk_level      TEXT,
    fto_blocking_patents TEXT,
    fto_checked         BOOLEAN DEFAULT 0,

    composite_score     REAL,
    tier_reached        INTEGER,
    run_date            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    machine_id          TEXT
);

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              INTEGER REFERENCES runs,
    drug_id             TEXT REFERENCES drugs,
    indication_id       TEXT REFERENCES indications,
    evidence_type       TEXT,
    source_type         TEXT,
    source_id           TEXT,
    title               TEXT,
    year                INTEGER,
    strength            TEXT,
    direction           TEXT,
    summary             TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS findings (
    finding_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title               TEXT,
    description         TEXT,
    drug_ids            TEXT,
    indication_ids      TEXT,
    statistical_support TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS receipts (
    receipt_id          TEXT PRIMARY KEY,
    machine_id          TEXT,
    batch_start         TIMESTAMP,
    batch_end           TIMESTAMP,
    n_pairs_processed   INTEGER,
    n_llm_calls         INTEGER,
    llm_cost_usd        REAL,
    status              TEXT,
    filepath            TEXT
);
"""


def _j(obj: Any) -> str | None:
    """Serialize to JSON string, return None for None."""
    return json.dumps(obj) if obj is not None else None


def _pj(s: str | None) -> Any:
    """Parse JSON string, return None for None."""
    return json.loads(s) if s else None


class RepurposingDB:
    """Single access point for all pipeline database operations."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA_SQL)
            # Migrate existing DBs: add FTO columns if absent
            for col, typedef in [
                ("fto_risk_level", "TEXT"),
                ("fto_blocking_patents", "TEXT"),
                ("fto_checked", "BOOLEAN DEFAULT 0"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE runs ADD COLUMN {col} {typedef}")
                except Exception:
                    pass  # column already exists

    # ------------------------------------------------------------------
    # Drugs
    # ------------------------------------------------------------------

    def upsert_drug(self, drug: dict) -> None:
        row = {k: _j(v) if isinstance(v, (list, dict)) else v for k, v in drug.items()}
        cols = ", ".join(row)
        placeholders = ", ".join(["?"] * len(row))
        updates = ", ".join(f"{k}=excluded.{k}" for k in row if k != "drug_id")
        sql = f"""
            INSERT INTO drugs ({cols}) VALUES ({placeholders})
            ON CONFLICT(drug_id) DO UPDATE SET {updates}
        """
        with self._conn() as conn:
            conn.execute(sql, list(row.values()))

    def get_drug(self, drug_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM drugs WHERE drug_id=?", (drug_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        for col in ("brand_names", "approved_indications", "black_box_warnings",
                    "contraindications", "serious_aes", "primary_targets", "all_targets", "pathway_ids"):
            d[col] = _pj(d.get(col))
        return d

    def get_all_drugs(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT drug_id FROM drugs").fetchall()
        return [self.get_drug(r["drug_id"]) for r in rows]

    # ------------------------------------------------------------------
    # Indications
    # ------------------------------------------------------------------

    def upsert_indication(self, indication: dict) -> None:
        row = {k: _j(v) if isinstance(v, (list, dict)) else v for k, v in indication.items()}
        cols = ", ".join(row)
        placeholders = ", ".join(["?"] * len(row))
        updates = ", ".join(f"{k}=excluded.{k}" for k in row if k != "indication_id")
        sql = f"""
            INSERT INTO indications ({cols}) VALUES ({placeholders})
            ON CONFLICT(indication_id) DO UPDATE SET {updates}
        """
        with self._conn() as conn:
            conn.execute(sql, list(row.values()))

    def get_indication(self, indication_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM indications WHERE indication_id=?", (indication_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        for col in ("disease_genes", "pathway_ids", "go_terms", "transcriptomic_sig"):
            d[col] = _pj(d.get(col))
        return d

    def get_all_indications(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT indication_id FROM indications").fetchall()
        return [self.get_indication(r["indication_id"]) for r in rows]

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------

    def upsert_run(self, run: dict) -> int:
        """Insert or update a run row. Returns the run_id."""
        json_cols = {"t1_pathway_overlap", "t1_polypharmacology", "t1_ae_profile",
                     "t1_evidence_papers", "t2_biomarkers", "t2_trial_design",
                     "t2_endpoints", "t2_population", "t2_competitive_landscape"}
        row = {k: _j(v) if k in json_cols and isinstance(v, (list, dict)) else v
               for k, v in run.items()}
        # Check existing
        drug_id = row.get("drug_id")
        indication_id = row.get("indication_id")
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT run_id FROM runs WHERE drug_id=? AND indication_id=?",
                (drug_id, indication_id)
            ).fetchone()
            if existing:
                run_id = existing["run_id"]
                set_clause = ", ".join(f"{k}=?" for k in row if k not in ("drug_id", "indication_id"))
                vals = [v for k, v in row.items() if k not in ("drug_id", "indication_id")]
                conn.execute(f"UPDATE runs SET {set_clause} WHERE run_id=?", vals + [run_id])
            else:
                row.pop("run_id", None)
                cols = ", ".join(row)
                placeholders = ", ".join(["?"] * len(row))
                cur = conn.execute(f"INSERT INTO runs ({cols}) VALUES ({placeholders})", list(row.values()))
                run_id = cur.lastrowid
        return run_id

    def get_runs_at_tier(self, min_tier: int) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM runs WHERE tier_reached >= ?", (min_tier,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Evidence
    # ------------------------------------------------------------------

    def insert_evidence(self, evidence: dict) -> None:
        cols = ", ".join(evidence)
        placeholders = ", ".join(["?"] * len(evidence))
        sql = f"INSERT OR IGNORE INTO evidence ({cols}) VALUES ({placeholders})"
        with self._conn() as conn:
            conn.execute(sql, list(evidence.values()))

    def get_evidence_for_run(self, run_id: int) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM evidence WHERE run_id=?", (run_id,)).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Trials
    # ------------------------------------------------------------------

    def upsert_trial(self, trial: dict) -> None:
        row = {k: v for k, v in trial.items()}
        cols = ", ".join(row)
        placeholders = ", ".join(["?"] * len(row))
        updates = ", ".join(f"{k}=excluded.{k}" for k in row if k != "trial_id")
        sql = f"""
            INSERT INTO trials ({cols}) VALUES ({placeholders})
            ON CONFLICT(trial_id) DO UPDATE SET {updates}
        """
        with self._conn() as conn:
            conn.execute(sql, list(row.values()))

    def update_fto(self, drug_id: str, indication_id: str, risk_level: str, blocking_patents: list) -> None:
        """Write FTO results for an existing drug-indication run."""
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE runs
                SET fto_risk_level=?, fto_blocking_patents=?, fto_checked=1
                WHERE drug_id=? AND indication_id=?
                """,
                (risk_level, json.dumps(blocking_patents), drug_id, indication_id),
            )

    def get_trials_for_pair(self, drug_id: str, indication_id: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM trials WHERE drug_id=? AND indication_id=?",
                (drug_id, indication_id)
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Findings
    # ------------------------------------------------------------------

    def insert_finding(self, finding: dict) -> None:
        row = {k: _j(v) if isinstance(v, list) else v for k, v in finding.items()}
        cols = ", ".join(row)
        placeholders = ", ".join(["?"] * len(row))
        sql = f"INSERT INTO findings ({cols}) VALUES ({placeholders})"
        with self._conn() as conn:
            conn.execute(sql, list(row.values()))

    def get_all_findings(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM findings ORDER BY finding_id").fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Pair generation
    # ------------------------------------------------------------------

    def get_all_drug_indication_pairs(self) -> list[dict]:
        """Cross-join drugs × indications — the screening universe."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT d.drug_id, i.indication_id FROM drugs d CROSS JOIN indications i"
            ).fetchall()
        return [{"drug_id": r["drug_id"], "indication_id": r["indication_id"]} for r in rows]

    # ------------------------------------------------------------------
    # Receipts
    # ------------------------------------------------------------------

    def insert_receipt(self, receipt: dict) -> None:
        cols = ", ".join(receipt)
        placeholders = ", ".join(["?"] * len(receipt))
        sql = f"INSERT OR REPLACE INTO receipts ({cols}) VALUES ({placeholders})"
        with self._conn() as conn:
            conn.execute(sql, list(receipt.values()))
