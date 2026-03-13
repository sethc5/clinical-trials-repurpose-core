"""
lincs_scorer.py — T0.25: Transcriptomic signature reversal scoring.

Computes LINCS L1000 reversal score: does the drug's gene expression
signature reverse the disease gene expression signature?

Positive reversal score → drug makes sick cells look more like healthy cells.
Validated repurposing method (Lamb et al. 2006, Corsello et al. 2020).
"""

from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)


def compute_transcriptomic_reversal(
    drug: dict,
    indication: dict,
    lincs_config,  # TranscriptomicConfig
) -> float | None:
    """
    Compute LINCS L1000 transcriptomic reversal score.

    Returns:
        Float in [-1, 1] where positive = reversal (therapeutic signal).
        None if drug or disease signature is not in LINCS database.
    """
    from adapters.lincs_adapter import LINCSAdapter

    lincs = LINCSAdapter()  # configured at pipeline init; uses module-level config

    drug_name = drug.get("name") or drug.get("generic_name") or drug.get("drug_id")
    drug_sig = lincs.get_drug_signature(drug_name)

    disease_sig = _get_disease_signature(indication)

    if drug_sig is None or disease_sig is None:
        log.debug(f"LINCS signature missing: drug={drug_name}, indication={indication.get('indication_id')}")
        return None

    # Check minimum genes matched threshold
    drug_genes = set(drug_sig.get("up_genes", [])) | set(drug_sig.get("down_genes", []))
    disease_genes = set(disease_sig.get("up_genes", [])) | set(disease_sig.get("down_genes", []))
    n_matched = len(drug_genes & disease_genes)

    if n_matched < lincs_config.min_genes_matched:
        log.debug(f"LINCS insufficient gene overlap: {n_matched} < {lincs_config.min_genes_matched}")
        return None

    score = lincs.compute_reversal_score(drug_sig, disease_sig)
    return round(score, 4)


def _get_disease_signature(indication: dict) -> dict | None:
    """
    Extract disease transcriptomic signature from indication record.

    The transcriptomic_sig field stores the disease expression signature
    (from GEO or DisGeNET transcriptomic data) as {up_genes, down_genes}.
    """
    sig_raw = indication.get("transcriptomic_sig")
    if not sig_raw:
        return None

    if isinstance(sig_raw, dict):
        return sig_raw
    if isinstance(sig_raw, str):
        try:
            return json.loads(sig_raw)
        except Exception:
            return None
    return None


def batch_score_drugs(
    drugs: list[dict],
    indication: dict,
    lincs_config,
    min_score: float = 0.0,
) -> list[dict]:
    """
    Score all drugs against an indication signature.

    Returns list of {drug_id, reversal_score} sorted by descending score.
    Useful for pre-scanning entire drug universe against one indication.
    """
    results = []
    disease_sig = _get_disease_signature(indication)
    if not disease_sig:
        log.warning(f"No disease signature for {indication.get('indication_id')} — skipping batch scoring")
        return []

    from adapters.lincs_adapter import LINCSAdapter
    lincs = LINCSAdapter()

    for drug in drugs:
        drug_name = drug.get("name") or drug.get("drug_id")
        drug_sig = lincs.get_drug_signature(drug_name)
        if not drug_sig:
            continue
        score = lincs.compute_reversal_score(drug_sig, disease_sig)
        if score >= min_score:
            results.append({"drug_id": drug["drug_id"], "reversal_score": score})

    return sorted(results, key=lambda x: -x["reversal_score"])
