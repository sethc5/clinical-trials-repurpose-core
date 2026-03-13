"""
polypharmacology_scorer.py — T1: Off-target effect relevance scoring.

Scores the relevance of a drug's known off-target interactions to the
target indication. Polypharmacology (hitting multiple relevant targets)
is often an advantage for repurposing, not a liability.
"""

from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger(__name__)


def score_polypharmacology(drug: dict, indication: dict) -> dict:
    """
    Evaluate polypharmacology profile of a drug against the target indication.

    For each off-target in the drug's profile:
      - Is it relevant to the indication's disease pathway?
      - Is it protective or harmful in the disease context?
      - What is the estimated affinity relative to primary target?

    Returns:
        {
            "n_targets": int,
            "relevant_off_targets": [{gene, affinity_rank, relevance, direction}],
            "synergy_score": float,  # 0-1, higher = more synergistic off-targets
            "risk_score": float,     # 0-1, higher = more harmful off-targets
        }
    """
    all_targets = _parse_targets(drug.get("all_targets"))
    primary_targets = _parse_targets(drug.get("primary_targets"))
    disease_genes = _disease_gene_set(indication)

    if not all_targets:
        return {
            "n_targets": 0,
            "relevant_off_targets": [],
            "synergy_score": 0.0,
            "risk_score": 0.0,
        }

    # Identify off-targets (non-primary)
    primary_gene_names = {t.get("gene_name") for t in primary_targets if t.get("gene_name")}
    off_targets = [t for t in all_targets if t.get("gene_name") not in primary_gene_names]

    # Score each off-target
    relevant = []
    synergy_hits = 0
    risk_hits = 0

    for target in off_targets:
        gene = target.get("gene_name")
        if not gene:
            continue

        in_disease_pathway = gene in disease_genes
        action = (target.get("action") or target.get("affinity") or "").lower()

        # Rough direction classification
        if any(w in action for w in ("inhibitor", "antagonist", "blocker")):
            direction = "inhibition"
        elif any(w in action for w in ("activator", "agonist", "inducer")):
            direction = "activation"
        else:
            direction = "unknown"

        relevance = "high" if in_disease_pathway else "low"

        if in_disease_pathway:
            relevant.append({
                "gene": gene,
                "action": action,
                "direction": direction,
                "relevance": relevance,
            })
            # Simple heuristic: inhibition of disease gene = potentially synergistic
            synergy_hits += 1

    n_targets = len(all_targets)
    synergy_score = min(1.0, synergy_hits / max(n_targets, 1) * 2)
    risk_score = 0.0  # populated by faers_miner.py

    return {
        "n_targets": n_targets,
        "n_primary_targets": len(primary_targets),
        "n_off_targets": len(off_targets),
        "relevant_off_targets": relevant[:10],
        "synergy_score": round(synergy_score, 3),
        "risk_score": round(risk_score, 3),
    }


def _parse_targets(field: Any) -> list[dict]:
    if not field:
        return []
    if isinstance(field, str):
        try:
            field = json.loads(field)
        except Exception:
            return []
    if isinstance(field, list):
        return [t for t in field if isinstance(t, dict)]
    return []


def _disease_gene_set(indication: dict) -> set[str]:
    disease_genes = indication.get("disease_genes")
    if not disease_genes:
        return set()
    if isinstance(disease_genes, str):
        try:
            disease_genes = json.loads(disease_genes)
        except Exception:
            return set()
    genes = set()
    for g in disease_genes:
        if isinstance(g, dict):
            sym = g.get("gene_symbol") or g.get("gene_name")
            if sym:
                genes.add(sym)
        elif isinstance(g, str):
            genes.add(g)
    return genes
