"""
pipeline_core.py — 4-tier repurposing screening funnel

Runs drug-indication pairs through T0 → T0.25 → T1 → T2.
Config-driven via config.yaml (validated by config_schema.py).
Writes results to SQLite (db_utils.py) and receipts (receipt_system.py).

Usage:
    python pipeline_core.py --config config.yaml --tier 025 -w 8
    python pipeline_core.py --config config.yaml -w 4 --llm-workers 3
"""

from __future__ import annotations

import argparse
import concurrent.futures
import logging
import time
from pathlib import Path
from typing import Optional

import yaml

from config_schema import PipelineConfig
from db_utils import RepurposingDB
from receipt_system import ReceiptSystem

# T0 compute
from compute.mechanism_overlap import compute_mechanism_overlap
from compute.safety_filter import check_safety_compatibility
from compute.trial_history_checker import check_trial_history
from compute.mesh_distance import compute_mesh_distance

# T0.25 compute
from compute.network_proximity import compute_network_proximity
from compute.lincs_scorer import compute_transcriptomic_reversal
from compute.literature_cooccurrence import count_pubmed_cooccurrence
from compute.failed_trial_classifier import classify_failed_trials

# T1 compute
from compute.pathway_analyzer import analyze_pathway_overlap
from compute.polypharmacology_scorer import score_polypharmacology
from compute.faers_miner import mine_adverse_events
from compute.evidence_extractor import extract_evidence
from compute.evidence_scorer import score_evidence

# T2 compute
from compute.evidence_synthesizer import synthesize_evidence
from compute.biomarker_identifier import identify_biomarkers
from compute.dose_analyzer import analyze_dose
from compute.trial_designer import design_trial
from compute.competitive_landscape import analyze_competitive_landscape
from compute.dossier_generator import generate_dossier
from adapters.fto_adapter import check_fto

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tier runners
# ---------------------------------------------------------------------------

def run_t0(pair: dict, config: PipelineConfig, db: RepurposingDB) -> dict:
    """
    T0: Mechanism overlap + basic safety filter.
    Milliseconds per pair — pure database lookup.
    """
    drug_id = pair["drug_id"]
    indication_id = pair["indication_id"]
    target = config.target

    result = {
        "drug_id": drug_id,
        "indication_id": indication_id,
        "t0_pass": False,
        "t0_mechanism_overlap": 0.0,
        "t0_safety_compatible": False,
        "t0_already_tried": False,
        "t0_reject_reason": None,
    }

    drug = db.get_drug(drug_id)
    indication = db.get_indication(indication_id)
    if not drug or not indication:
        result["t0_reject_reason"] = "missing_data"
        return result

    # Check already tried / approved
    already_tried = check_trial_history(drug_id, indication_id, db)
    result["t0_already_tried"] = already_tried
    if already_tried and config.filters.t0.exclude_active_trials_same_indication:
        result["t0_reject_reason"] = "already_in_trials"
        return result

    # Safety compatibility
    safety_ok = check_safety_compatibility(drug, indication, target, config.filters.t0)
    result["t0_safety_compatible"] = safety_ok
    if not safety_ok:
        result["t0_reject_reason"] = "safety_incompatible"
        return result

    # Mechanism overlap
    overlap = compute_mechanism_overlap(drug, indication, config.filters.t0)
    result["t0_mechanism_overlap"] = overlap
    if (
        config.filters.t0.require_mechanism_pathway_overlap
        and overlap < config.filters.t0.min_pathway_overlap_jaccard
    ):
        result["t0_reject_reason"] = "insufficient_mechanism_overlap"
        return result

    result["t0_pass"] = True
    return result


def run_t025(pair: dict, config: PipelineConfig, db: RepurposingDB) -> dict:
    """
    T0.25: Network proximity + transcriptomic signature + literature co-occurrence.
    Seconds per pair.
    """
    drug = db.get_drug(pair["drug_id"])
    indication = db.get_indication(pair["indication_id"])
    f = config.filters.t025

    result = {
        "t025_pass": False,
        "t025_network_proximity": None,
        "t025_transcriptomic_score": None,
        "t025_literature_cooccurrence": 0,
        "t025_failed_trial": False,
        "t025_failed_trial_id": None,
    }

    # Network proximity (STRING PPI shortest path)
    proximity = compute_network_proximity(drug, indication, f.network_proximity)
    result["t025_network_proximity"] = proximity

    # Transcriptomic reversal (LINCS L1000)
    lincs_score = compute_transcriptomic_reversal(drug, indication, f.transcriptomic)
    result["t025_transcriptomic_score"] = lincs_score

    # Literature co-occurrence (PubMed abstracts)
    cooccurrence = count_pubmed_cooccurrence(drug["name"], indication["name"], f.literature)
    result["t025_literature_cooccurrence"] = cooccurrence

    # Failed trial check
    failed_trial = classify_failed_trials(pair["drug_id"], pair["indication_id"], db)
    result["t025_failed_trial"] = failed_trial.get("failed", False)
    result["t025_failed_trial_id"] = failed_trial.get("trial_id")

    # Promote criterion: network proximity OR transcriptomic reversal above threshold
    prox_pass = (
        proximity is not None
        and proximity <= f.network_proximity.max_shortest_path
    )
    lincs_pass = (
        lincs_score is not None
        and lincs_score >= f.transcriptomic.min_reversal_score
    )
    lit_pass = cooccurrence >= f.literature.min_cooccurrence

    result["t025_pass"] = prox_pass or lincs_pass or lit_pass
    return result


def run_t1(pair: dict, config: PipelineConfig, db: RepurposingDB) -> dict:
    """
    T1: Deep mechanistic analysis + evidence extraction. Minutes per pair.
    """
    drug = db.get_drug(pair["drug_id"])
    indication = db.get_indication(pair["indication_id"])
    f = config.filters.t1

    pathway_overlap = analyze_pathway_overlap(drug, indication)
    poly_score = score_polypharmacology(drug, indication)
    ae_profile = mine_adverse_events(pair["drug_id"], indication)
    evidence_items = extract_evidence(drug, indication, max_papers=f.max_papers_to_extract, model=f.llm_model)
    evidence_score, mechanistic_score, safety_score = score_evidence(
        evidence_items, pathway_overlap, poly_score, ae_profile
    )

    # Persist evidence items
    for item in evidence_items:
        db.insert_evidence({**item, "drug_id": pair["drug_id"], "indication_id": pair["indication_id"]})

    t1_pass = (
        evidence_score >= f.min_evidence_score
        and mechanistic_score >= f.min_mechanistic_score
        and safety_score >= f.min_safety_score
    )

    return {
        "t1_pass": t1_pass,
        "t1_pathway_overlap": pathway_overlap,
        "t1_polypharmacology": poly_score,
        "t1_ae_profile": ae_profile,
        "t1_evidence_papers": [e["source_id"] for e in evidence_items],
        "t1_evidence_score": evidence_score,
        "t1_mechanistic_score": mechanistic_score,
        "t1_safety_score": safety_score,
    }


def run_t2(pair: dict, config: PipelineConfig, db: RepurposingDB) -> dict:
    """
    T2: Full evidence synthesis + trial design. Hours per pair (LLM-heavy).
    """
    drug = db.get_drug(pair["drug_id"])
    indication = db.get_indication(pair["indication_id"])
    f = config.filters.t2
    model = f.llm_model

    evidence_summary = synthesize_evidence(drug, indication, db, model)
    biomarkers = identify_biomarkers(drug, indication, model)
    dose_rationale = analyze_dose(drug, indication, model)
    trial_design = design_trial(drug, indication, config.target, model)
    landscape = analyze_competitive_landscape(drug, indication, model)

    confidence = pair.get("t1_evidence_score", 0) * 0.4 + pair.get("t1_mechanistic_score", 0) * 0.4
    novelty = 1.0 - (0.5 if pair.get("t025_failed_trial") else 0.0)

    t2_pass = confidence >= f.min_confidence

    if t2_pass and config.output.export_dossiers:
        generate_dossier(drug, indication, evidence_summary, trial_design, config)

    # FTO check — non-blocking; returns UNKNOWN if service is down
    fto = check_fto(
        drug_name=drug.get("name") or drug["drug_id"],
        indication=indication.get("name") or indication["indication_id"],
        smiles=drug.get("smiles"),
        client_ref=f"{drug['drug_id']}::{indication['indication_id']}",
    )
    if fto.risk_level != "UNKNOWN":
        db.update_fto(
            drug["drug_id"], indication["indication_id"],
            fto.risk_level, fto.blocking_patents,
        )
    if fto.risk_level == "HIGH":
        log.warning(
            "HIGH FTO risk for %s → %s: %d blocking patent(s)",
            drug.get("name", drug["drug_id"]),
            indication.get("name", indication["indication_id"]),
            len(fto.blocking_patents),
        )

    return {
        "t2_pass": t2_pass,
        "t2_evidence_summary": evidence_summary,
        "t2_biomarkers": biomarkers,
        "t2_dose_rationale": dose_rationale,
        "t2_trial_design": trial_design,
        "t2_competitive_landscape": landscape,
        "t2_confidence": confidence,
        "t2_novelty": novelty,
        "fto_risk_level": fto.risk_level,
    }


# ---------------------------------------------------------------------------
# Main pipeline runner
# ---------------------------------------------------------------------------

def run_pipeline(config: PipelineConfig, max_tier: str = "2", workers: int = 4, llm_workers: int = 2) -> None:
    db = RepurposingDB(config.output.db_path)
    db.init_schema()
    receipt = ReceiptSystem(config.output.receipts_dir)

    pairs = db.get_all_drug_indication_pairs()
    log.info(f"Starting pipeline: {len(pairs)} pairs, max tier T{max_tier}")

    batch_start = time.time()
    n_llm_calls = 0
    llm_cost = 0.0

    # --- T0 ---
    t0_survivors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(run_t0, p, config, db): p for p in pairs}
        for fut in concurrent.futures.as_completed(futures):
            res = fut.result()
            db.upsert_run(res)
            if res["t0_pass"]:
                t0_survivors.append(res)

    log.info(f"T0: {len(t0_survivors)}/{len(pairs)} passed")
    if max_tier == "0":
        receipt.write(batch_start, len(pairs), n_llm_calls, llm_cost)
        return

    # --- T0.25 ---
    t025_survivors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(run_t025, p, config, db): p for p in t0_survivors}
        for fut in concurrent.futures.as_completed(futures):
            res = {**futures[fut], **fut.result()}
            db.upsert_run(res)
            if res["t025_pass"]:
                t025_survivors.append(res)

    log.info(f"T0.25: {len(t025_survivors)}/{len(t0_survivors)} passed")
    if max_tier == "025":
        receipt.write(batch_start, len(pairs), n_llm_calls, llm_cost)
        return

    # --- T1 ---
    t1_survivors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=llm_workers) as executor:
        futures = {executor.submit(run_t1, p, config, db): p for p in t025_survivors}
        for fut in concurrent.futures.as_completed(futures):
            res = {**futures[fut], **fut.result()}
            db.upsert_run(res)
            n_llm_calls += config.filters.t1.max_papers_to_extract
            if res["t1_pass"]:
                t1_survivors.append(res)

    log.info(f"T1: {len(t1_survivors)}/{len(t025_survivors)} passed")
    if max_tier == "1":
        receipt.write(batch_start, len(pairs), n_llm_calls, llm_cost)
        return

    # --- T2 ---
    t2_survivors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=llm_workers) as executor:
        futures = {executor.submit(run_t2, p, config, db): p for p in t1_survivors}
        for fut in concurrent.futures.as_completed(futures):
            res = {**futures[fut], **fut.result()}
            db.upsert_run(res)
            n_llm_calls += 10  # approximate
            llm_cost += 0.75   # approximate per T2 dossier
            if res["t2_pass"]:
                t2_survivors.append(res)

    log.info(f"T2: {len(t2_survivors)}/{len(t1_survivors)} passed")
    receipt.write(batch_start, len(pairs), n_llm_calls, llm_cost)
    log.info(f"Pipeline complete. Top candidates: {len(t2_survivors)}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Clinical trial repurposing pipeline")
    parser.add_argument("--config", required=True, help="Path to config YAML")
    parser.add_argument("--tier", default="2", choices=["0", "025", "1", "2"],
                        help="Maximum tier to run (default: 2 = full pipeline)")
    parser.add_argument("-w", "--workers", type=int, default=8)
    parser.add_argument("--llm-workers", type=int, default=3)
    args = parser.parse_args()

    raw = yaml.safe_load(Path(args.config).read_text())
    config = PipelineConfig(**raw)
    run_pipeline(config, max_tier=args.tier, workers=args.workers, llm_workers=args.llm_workers)


if __name__ == "__main__":
    main()
