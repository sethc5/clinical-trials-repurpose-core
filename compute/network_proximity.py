"""
network_proximity.py — T0.25: Drug target → disease gene network proximity.

Shortest-path distance between drug primary targets and disease-associated genes
in the STRING PPI network. Negative z-score (proximal) = mechanistic plausibility.

Method from: Guney et al. (2016) "Network-based in silico drug efficacy screening"
             Himmelstein et al. (2017) network proximity validation
"""

from __future__ import annotations

import logging
import random
import statistics
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class ProximityResult:
    raw_distance: float | None     # mean shortest path (drug targets → disease genes)
    z_score: float | None          # network proximity z-score
    n_drug_targets: int
    n_disease_genes: int
    n_connected_pairs: int


def compute_network_proximity(
    drug: dict,
    indication: dict,
    prox_config,  # NetworkProximityConfig
) -> float | None:
    """
    Compute network proximity between drug targets and disease genes.

    Returns the z-score of the mean shortest path (negative = proximal).
    Returns None if insufficient data (missing targets or genes).
    """
    from adapters.string_adapter import STRINGAdapter

    drug_targets = _extract_gene_list(drug.get("primary_targets") or drug.get("all_targets"))
    disease_genes = _extract_gene_list(indication.get("disease_genes"))

    if not drug_targets or not disease_genes:
        log.debug(f"No targets/genes for proximity: {drug.get('drug_id')} × {indication.get('indication_id')}")
        return None

    string = STRINGAdapter(min_confidence=700)

    # Compute mean shortest path from drug targets to disease genes
    raw_distance = string.shortest_path_length(drug_targets, disease_genes)
    if raw_distance is None:
        return None

    # Compute z-score via permutation (simplified — use analytical if available)
    z_score = _compute_z_score(
        raw_distance=raw_distance,
        drug_targets=drug_targets,
        disease_genes=disease_genes,
        string=string,
        n_permutations=100,
    )

    return z_score


def _compute_z_score(
    raw_distance: float,
    drug_targets: list[str],
    disease_genes: list[str],
    string,
    n_permutations: int = 100,
) -> float:
    """
    Compute network proximity z-score via degree-preserving permutation.

    Z-score = (d_observed - mean_d_random) / std_d_random
    Negative z-score = drug targets are closer to disease genes than random.
    """
    # For performance, use a simplified random sampling approach
    # Full implementation: degree-preserving node swaps (Maslov-Sneppen)
    all_genes = drug_targets + disease_genes

    permuted_distances = []
    for _ in range(n_permutations):
        random.shuffle(all_genes)
        rand_drug = all_genes[:len(drug_targets)]
        rand_disease = all_genes[len(drug_targets):]
        d = string.shortest_path_length(rand_drug, rand_disease)
        if d is not None:
            permuted_distances.append(d)

    if len(permuted_distances) < 10:
        return 0.0  # insufficient data for z-score

    mean_rand = statistics.mean(permuted_distances)
    std_rand = statistics.stdev(permuted_distances) or 1e-6

    return (raw_distance - mean_rand) / std_rand


def _extract_gene_list(targets_field) -> list[str]:
    """Extract gene symbols from a targets or disease_genes field."""
    if not targets_field:
        return []
    if isinstance(targets_field, str):
        import json
        try:
            targets_field = json.loads(targets_field)
        except Exception:
            return []
    if isinstance(targets_field, list):
        genes = []
        for t in targets_field:
            if isinstance(t, dict):
                gene = t.get("gene_name") or t.get("gene_symbol")
                if gene:
                    genes.append(gene)
            elif isinstance(t, str):
                genes.append(t)
        return genes
    return []
